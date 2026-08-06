"""DB 계약 fail-closed 검증 (1단계).

권위: docs/contracts/db-contract.md §3 (V-01 ~ V-12)
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §21

목적:
  기대한 스키마·권한과 실제 DB 가 다르면 **기능을 열지 않고 기동을 실패시킨다.**
  조용한 폴백(컬럼 없으면 NULL 취급 등)을 만들지 않는다. 드리프트를 숨긴다.

주의:
  - 파티션은 부모의 CHECK 제약을 복제한다. conrelid 를 함께 지정한다.
  - 테이블 소유자는 컬럼 단위 GRANT 를 우회한다. 수집기 테이블을 Web 롤이
    소유하지 않는지도 확인한다.
  - 권한 거부 판정을 오류 메시지 문자열로 하지 않는다. 로케일에 따라 달라진다.

모든 SQL 값은 파라미터 바인딩으로만 전달한다. 식별자를 외부 입력으로 받지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from lifelaw_web.db import contract

if TYPE_CHECKING:
    import psycopg

WEB_TABLE_PREFIX: Final = "tw\\_%"


class SchemaContractError(RuntimeError):
    """계약 불일치. 기동을 중단시킨다."""

    def __init__(self, failures: list[CheckResult]) -> None:
        self.failures = failures
        summary = "; ".join(f"{f.check_id} {f.title}: {f.detail}" for f in failures)
        super().__init__(f"DB 계약 검증 실패 {len(failures)}건 — {summary}")


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    title: str
    ok: bool
    detail: str
    informational: bool = False
    data: tuple[str, ...] = field(default_factory=tuple)


def _ok(check_id: str, title: str, detail: str = "일치") -> CheckResult:
    return CheckResult(check_id, title, True, detail)


def _fail(check_id: str, title: str, detail: str) -> CheckResult:
    return CheckResult(check_id, title, False, detail)


# ---------------------------------------------------------------------------
# V-01  테이블 존재
# ---------------------------------------------------------------------------


def check_tables(conn: psycopg.Connection[tuple[object, ...]]) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_tables
             WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (list(contract.COLLECTOR_TABLES),),
        )
        present = {str(r[0]) for r in cur.fetchall()}
    missing = sorted(set(contract.COLLECTOR_TABLES) - present)
    if missing:
        return _fail("V-01", "수집기 테이블 존재", f"없는 테이블: {', '.join(missing)}")
    return _ok("V-01", "수집기 테이블 존재", f"{len(present)}개 확인")


# ---------------------------------------------------------------------------
# V-02  allowlist 컬럼 존재
# ---------------------------------------------------------------------------


def check_writable_columns_exist(conn: psycopg.Connection[tuple[object, ...]]) -> CheckResult:
    missing: list[str] = []
    with conn.cursor() as cur:
        for table, columns in contract.WRITABLE_COLUMNS.items():
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = %s
                """,
                (table,),
            )
            present = {str(r[0]) for r in cur.fetchall()}
            missing.extend(f"{table}.{c}" for c in sorted(columns - present))
    if missing:
        return _fail("V-02", "쓰기 allowlist 컬럼 존재", f"없는 컬럼: {', '.join(missing)}")
    total = sum(len(c) for c in contract.WRITABLE_COLUMNS.values())
    return _ok("V-02", "쓰기 allowlist 컬럼 존재", f"{total}개 확인")


# ---------------------------------------------------------------------------
# V-03  계산 컬럼이 STORED GENERATED
# V-04  수식의 run 항 유무
# ---------------------------------------------------------------------------


def check_generated_columns(conn: psycopg.Connection[tuple[object, ...]]) -> list[CheckResult]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname, a.attgenerated,
                   coalesce(pg_get_expr(d.adbin, d.adrelid), '')
              FROM pg_attribute a
              LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE a.attrelid = 'tn_crawl_target'::regclass
               AND a.attname = ANY(%s)
               AND a.attnum > 0 AND NOT a.attisdropped
            """,
            (list(contract.GENERATED_COLUMNS),),
        )
        found = {str(r[0]): (str(r[1]), str(r[2])) for r in cur.fetchall()}

    stored_problems: list[str] = []
    run_problems: list[str] = []
    for column, expects_run_term in contract.GENERATED_COLUMNS.items():
        entry = found.get(column)
        if entry is None:
            stored_problems.append(f"{column} 없음")
            continue
        generated, expression = entry
        if generated != "s":
            stored_problems.append(f"{column} attgenerated={generated!r} (기대 's')")
        has_run_term = "run_collect_policy_cd" in expression
        if has_run_term is not expects_run_term:
            run_problems.append(
                f"{column} run항={has_run_term} (기대 {expects_run_term})"
            )

    results = []
    results.append(
        _fail("V-03", "계산 컬럼 STORED GENERATED", ", ".join(stored_problems))
        if stored_problems
        else _ok("V-03", "계산 컬럼 STORED GENERATED", f"{len(found)}개 확인")
    )
    results.append(
        _fail("V-04", "계산 컬럼 수식의 run 항", ", ".join(run_problems))
        if run_problems
        else _ok(
            "V-04",
            "계산 컬럼 수식의 run 항",
            "effective=구성정책만, execution=run 포함",
        )
    )
    return results


# ---------------------------------------------------------------------------
# V-05  공통 코드값
# ---------------------------------------------------------------------------


def check_common_codes(conn: psycopg.Connection[tuple[object, ...]]) -> CheckResult:
    expected = {(grp, val) for grp, vals in contract.REQUIRED_CODES.items() for val in vals}
    with conn.cursor() as cur:
        cur.execute("SELECT code_grp_cd, code_val, use_yn FROM tc_common_code")
        rows = [(str(r[0]), str(r[1]), str(r[2])) for r in cur.fetchall()]

    present = {(g, v) for g, v, _ in rows}
    missing = sorted(expected - present)
    unused = sorted((g, v) for g, v, u in rows if (g, v) in expected and u != "Y")

    problems: list[str] = []
    if missing:
        problems.append("없는 코드: " + ", ".join(f"{g}/{v}" for g, v in missing))
    if unused:
        problems.append("use_yn<>'Y': " + ", ".join(f"{g}/{v}" for g, v in unused))
    if problems:
        return _fail("V-05", "공통 코드값", "; ".join(problems))
    return _ok("V-05", "공통 코드값", f"{contract.REQUIRED_CODE_COUNT}건 확인, 전부 use_yn='Y'")


# ---------------------------------------------------------------------------
# V-06  TH 가 파티션 테이블
# V-07  파티션 목록 (조회 가능 범위 — 실패 아님)
# ---------------------------------------------------------------------------


def check_partitioning(conn: psycopg.Connection[tuple[object, ...]]) -> list[CheckResult]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT relkind FROM pg_class WHERE relname = %s",
            (contract.PARTITIONED_TABLE,),
        )
        row = cur.fetchone()
        relkind = str(row[0]) if row else ""

        cur.execute(
            """
            SELECT c.relname
              FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid
             WHERE i.inhparent = %s::regclass
             ORDER BY c.relname
            """,
            (contract.PARTITIONED_TABLE,),
        )
        partitions = tuple(str(r[0]) for r in cur.fetchall())

    v06 = (
        _ok("V-06", "이력 테이블 파티셔닝", "relkind='p'")
        if relkind == "p"
        else _fail("V-06", "이력 테이블 파티셔닝", f"relkind={relkind!r} (기대 'p')")
    )
    v07 = CheckResult(
        "V-07",
        "조회 가능 파티션",
        ok=True,
        detail=(", ".join(partitions) if partitions else "파티션 없음 — 이력 조회 결과는 0건"),
        informational=True,
        data=partitions,
    )
    return [v06, v07]


# ---------------------------------------------------------------------------
# V-08  CHECK 제약 (conrelid 지정)
# ---------------------------------------------------------------------------


def check_constraints(conn: psycopg.Connection[tuple[object, ...]]) -> CheckResult:
    missing: list[str] = []
    with conn.cursor() as cur:
        for table, conname in contract.REQUIRED_CHECK_CONSTRAINTS:
            cur.execute(
                """
                SELECT 1 FROM pg_constraint
                 WHERE contype = 'c' AND conname = %s AND conrelid = %s::regclass
                """,
                (conname, table),
            )
            if cur.fetchone() is None:
                missing.append(f"{table}.{conname}")
    if missing:
        return _fail("V-08", "CHECK 제약", f"없는 제약: {', '.join(missing)}")
    return _ok(
        "V-08",
        "CHECK 제약",
        f"{len(contract.REQUIRED_CHECK_CONSTRAINTS)}개 확인 (conrelid 지정)",
    )


# ---------------------------------------------------------------------------
# V-09  append-only 테이블에 UPDATE/DELETE 권한이 없어야 함
# ---------------------------------------------------------------------------


def check_append_only_privileges(
    conn: psycopg.Connection[tuple[object, ...]], role: str
) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, privilege_type
              FROM information_schema.table_privileges
             WHERE grantee = %s
               AND table_name = ANY(%s)
               AND privilege_type IN ('UPDATE', 'DELETE')
             ORDER BY table_name, privilege_type
            """,
            (role, list(contract.APPEND_ONLY_TABLES)),
        )
        granted = [f"{r[0]}.{r[1]}" for r in cur.fetchall()]
    if granted:
        return _fail(
            "V-09",
            "append-only 권한",
            f"{role} 에 부여되어 있음: {', '.join(granted)}",
        )
    return _ok(
        "V-09",
        "append-only 권한",
        f"{', '.join(contract.APPEND_ONLY_TABLES)} 에 UPDATE/DELETE 없음",
    )


# ---------------------------------------------------------------------------
# V-10   allowlist 컬럼에만 UPDATE 권한
# V-10b  금지 컬럼에 UPDATE 권한 없음
# ---------------------------------------------------------------------------


def check_column_privileges(
    conn: psycopg.Connection[tuple[object, ...]], role: str
) -> list[CheckResult]:
    results: list[CheckResult] = []
    forbidden_granted: list[str] = []

    with conn.cursor() as cur:
        for table, allowed in contract.WRITABLE_COLUMNS.items():
            cur.execute(
                """
                SELECT column_name FROM information_schema.column_privileges
                 WHERE grantee = %s AND table_name = %s AND privilege_type = 'UPDATE'
                """,
                (role, table),
            )
            granted = {str(r[0]) for r in cur.fetchall()}

            extra = sorted(granted - allowed)
            lacking = sorted(allowed - granted)
            problems: list[str] = []
            if extra:
                problems.append(f"허용 밖 컬럼에 권한: {', '.join(extra)}")
            if lacking:
                problems.append(f"필요한 권한 없음: {', '.join(lacking)}")
            results.append(
                _fail("V-10", f"{table} UPDATE 권한 범위", "; ".join(problems))
                if problems
                else _ok("V-10", f"{table} UPDATE 권한 범위", f"allowlist {len(allowed)}개와 일치")
            )
            forbidden_granted.extend(
                f"{table}.{c}" for c in sorted(granted & contract.FORBIDDEN_UPDATE_COLUMNS)
            )

    results.append(
        _fail("V-10b", "금지 컬럼 UPDATE 권한", f"부여되어 있음: {', '.join(forbidden_granted)}")
        if forbidden_granted
        else _ok(
            "V-10b",
            "금지 컬럼 UPDATE 권한",
            f"금지 {len(contract.FORBIDDEN_UPDATE_COLUMNS)}개 컬럼에 권한 없음",
        )
    )
    return results


# ---------------------------------------------------------------------------
# V-11  마이그레이션 버전
# ---------------------------------------------------------------------------


def check_migration_version(conn: psycopg.Connection[tuple[object, ...]]) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute("SELECT max(version) FROM tw_schema_migration")
        row = cur.fetchone()
    applied = str(row[0]) if row and row[0] is not None else ""
    if applied != contract.EXPECTED_MIGRATION_VERSION:
        return _fail(
            "V-11",
            "마이그레이션 버전",
            f"적용={applied or '없음'} 기대={contract.EXPECTED_MIGRATION_VERSION}",
        )
    return _ok("V-11", "마이그레이션 버전", applied)


# ---------------------------------------------------------------------------
# 보강  수집기 테이블 소유자가 Web 롤이 아님
#
# 테이블 소유자는 컬럼 단위 GRANT 를 우회한다. 이 검사가 없으면 V-10/V-10b 가
# 통과해도 실제로는 아무 통제가 없는 상태일 수 있다.
# ---------------------------------------------------------------------------


def check_collector_table_owner(
    conn: psycopg.Connection[tuple[object, ...]], role: str
) -> CheckResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, pg_get_userbyid(c.relowner)
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
               AND c.relname = ANY(%s)
            """,
            (list(contract.COLLECTOR_TABLES),),
        )
        owned = [str(r[0]) for r in cur.fetchall() if str(r[1]) == role]
    if owned:
        return _fail(
            "V-OWN",
            "수집기 테이블 소유자",
            f"{role} 이 소유하고 있어 컬럼 단위 GRANT 가 무효: {', '.join(sorted(owned))}",
        )
    return _ok("V-OWN", "수집기 테이블 소유자", f"{role} 이 소유한 수집기 테이블 없음")


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def run_all(conn: psycopg.Connection[tuple[object, ...]], role: str) -> list[CheckResult]:
    """모든 검증을 수행하고 결과를 순서대로 돌려준다. 예외를 던지지 않는다."""
    results: list[CheckResult] = [
        check_tables(conn),
        check_writable_columns_exist(conn),
    ]
    results.extend(check_generated_columns(conn))
    results.append(check_common_codes(conn))
    results.extend(check_partitioning(conn))
    results.append(check_constraints(conn))
    results.append(check_append_only_privileges(conn, role))
    results.extend(check_column_privileges(conn, role))
    results.append(check_migration_version(conn))
    results.append(check_collector_table_owner(conn, role))
    return results


def assert_contract(conn: psycopg.Connection[tuple[object, ...]], role: str) -> list[CheckResult]:
    """검증 후 실패가 하나라도 있으면 SchemaContractError 를 던진다.

    기동 경로에서 호출한다. 실패를 무시하고 기능을 열지 않는다.
    """
    results = run_all(conn, role)
    failures = [r for r in results if not r.ok and not r.informational]
    if failures:
        raise SchemaContractError(failures)
    return results
