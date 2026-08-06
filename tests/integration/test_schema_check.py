"""DB 계약 검증 통합 테스트.

권위: docs/contracts/db-contract.md §3

**검증기가 통과하는 것만 확인하면 부족하다.** 실패를 실제로 잡아내는지도
확인해야 한다. 그래서 아래에는 계약을 일부러 어긋나게 만들어 FAIL 이 나오는지
보는 음성 테스트가 함께 있다.

권한 거부 판정은 종료 코드·SQLSTATE 로 한다. 오류 메시지 문자열로 판정하지
않는다 — PostgreSQL 메시지는 로케일에 따라 달라진다(한국어는 "접근 권한 없음").
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from lifelaw_web.db import contract, schema_check
from lifelaw_web.db.connection import session_time_zone

pytestmark = pytest.mark.integration

INSUFFICIENT_PRIVILEGE = "42501"
GENERATED_ALWAYS = "428C9"


# ---------------------------------------------------------------------------
# 통과 경로
# ---------------------------------------------------------------------------


def test_all_contract_checks_pass(conn: Any, runtime_role: str) -> None:
    results = schema_check.assert_contract(conn, runtime_role)
    failures = [r for r in results if not r.ok and not r.informational]
    assert failures == []
    assert len(results) >= 13


def test_session_time_zone_is_pinned(conn: Any) -> None:
    """서버 기본값에 의존하지 않고 Asia/Seoul 로 고정된다(D-26)."""
    assert session_time_zone(conn) == "Asia/Seoul"


def test_partition_list_is_informational_not_failing(conn: Any, runtime_role: str) -> None:
    """파티션 부재는 실패가 아니라 조회 가능 범위 정보다."""
    results = schema_check.run_all(conn, runtime_role)
    v07 = next(r for r in results if r.check_id == "V-07")
    assert v07.informational is True
    assert v07.ok is True


def test_migration_version_matches_expectation(conn: Any) -> None:
    result = schema_check.check_migration_version(conn)
    assert result.ok
    assert result.detail == contract.EXPECTED_MIGRATION_VERSION


def test_runtime_role_does_not_own_collector_tables(conn: Any, runtime_role: str) -> None:
    """소유자는 컬럼 단위 GRANT 를 우회한다. 소유하면 통제가 전부 무효다."""
    assert schema_check.check_collector_table_owner(conn, runtime_role).ok


# ---------------------------------------------------------------------------
# 음성 경로 — 검증기가 실패를 잡아내는가
# ---------------------------------------------------------------------------


def test_missing_table_is_detected(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        contract, "COLLECTOR_TABLES", (*contract.COLLECTOR_TABLES, "tn_does_not_exist")
    )
    result = schema_check.check_tables(conn)
    assert not result.ok
    assert "tn_does_not_exist" in result.detail


def test_missing_code_value_is_detected(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = {**contract.REQUIRED_CODES, "CRAWL_STAT": ("1010", "9999")}
    monkeypatch.setattr(contract, "REQUIRED_CODES", codes)
    result = schema_check.check_common_codes(conn)
    assert not result.ok
    assert "CRAWL_STAT/9999" in result.detail


def test_missing_check_constraint_is_detected(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        contract,
        "REQUIRED_CHECK_CONSTRAINTS",
        (*contract.REQUIRED_CHECK_CONSTRAINTS, ("tn_crawl_target", "ck_not_there")),
    )
    result = schema_check.check_constraints(conn)
    assert not result.ok
    assert "ck_not_there" in result.detail


def test_check_constraint_on_wrong_table_is_detected(
    conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이름은 존재하지만 대상 테이블이 다르면 실패해야 한다.

    파티션이 CHECK 제약을 복제하기 때문에 conrelid 없이 세면 이런 오류를 놓친다.
    """
    monkeypatch.setattr(
        contract,
        "REQUIRED_CHECK_CONSTRAINTS",
        (("tn_batch_run", "ck_crawl_target_diag"),),
    )
    result = schema_check.check_constraints(conn)
    assert not result.ok


def test_wrong_migration_version_is_detected(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contract, "EXPECTED_MIGRATION_VERSION", "9999")
    result = schema_check.check_migration_version(conn)
    assert not result.ok
    assert "9999" in result.detail


def test_forbidden_column_in_allowlist_is_detected(
    conn: Any, runtime_role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """allowlist 에 실행 상태 컬럼이 섞이면 V-10 이 '필요한 권한 없음'으로 잡는다."""
    writable = {
        **contract.WRITABLE_COLUMNS,
        "tn_crawl_target": contract.WRITABLE_COLUMNS["tn_crawl_target"] | {"crawl_stat_cd"},
    }
    monkeypatch.setattr(contract, "WRITABLE_COLUMNS", writable)
    results = schema_check.check_column_privileges(conn, runtime_role)
    v10 = next(r for r in results if r.check_id == "V-10" and "tn_crawl_target" in r.title)
    assert not v10.ok
    assert "crawl_stat_cd" in v10.detail


def test_owner_check_detects_web_owned_collector_table(conn: Any) -> None:
    """실제 소유자 이름을 넣으면 V-OWN 이 실패해야 한다."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname = %s",
            ("tn_crawl_target",),
        )
        row = cur.fetchone()
    owner = str(row[0])
    result = schema_check.check_collector_table_owner(conn, owner)
    assert not result.ok
    assert "tn_crawl_target" in result.detail


def test_assert_contract_raises_on_failure(
    conn: Any, runtime_role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(contract, "EXPECTED_MIGRATION_VERSION", "9999")
    with pytest.raises(schema_check.SchemaContractError) as exc:
        schema_check.assert_contract(conn, runtime_role)
    assert any(f.check_id == "V-11" for f in exc.value.failures)


# ---------------------------------------------------------------------------
# 실제 권한이 DB 에서 강제되는가 (SQLSTATE 판정)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE tn_crawl_target SET crawl_stat_cd = '1020'",
        "UPDATE tn_crawl_target SET change_yn_cd = '5020'",
        "UPDATE tn_crawl_target SET run_collect_policy_cd = '7020'",
        "UPDATE tn_crawl_target SET extract_method_cd = 'x'",
        "UPDATE tn_crawl_target SET file_format_cd = 'x'",
        "UPDATE tn_crawl_target SET batch_ymd = '20260101'",
        "DELETE FROM tn_crawl_target",
        "UPDATE th_crawl_target SET crawl_stat_cd = '1020'",
        "INSERT INTO tn_batch_run (batch_ymd, run_mode) VALUES ('20260806', 'fresh')",
        "UPDATE tc_common_code SET use_yn = 'N'",
        "UPDATE tw_audit_log SET actor = 'x'",
        "DELETE FROM tw_audit_log",
        "UPDATE tw_approval SET decision_cd = 'APPROVED'",
        "UPDATE tw_admin_command SET payload = '{}'::jsonb",
        "UPDATE tw_session SET user_id = 1",
    ],
)
def test_forbidden_statement_is_denied_by_database(conn: Any, statement: str) -> None:
    """애플리케이션 규율이 아니라 DB 권한이 막는지 확인한다."""
    with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege) as exc:
        cur.execute(statement)
    assert exc.value.sqlstate == INSUFFICIENT_PRIVILEGE
    conn.rollback()


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT count(*) FROM tc_common_code",
        "SELECT count(*) FROM tn_crawl_target",
        "SELECT count(*) FROM th_crawl_target",
        "SELECT count(*) FROM tn_batch_run",
        "SELECT count(*) FROM tn_cnpcls_cnlnk",
        "SELECT count(*) FROM tn_collect_site_policy",
        "SELECT count(*) FROM tw_user",
        "SELECT version FROM tw_schema_migration",
    ],
)
def test_read_paths_are_allowed(conn: Any, statement: str) -> None:
    with conn.cursor() as cur:
        cur.execute(statement)
        assert cur.fetchone() is not None


@pytest.mark.parametrize("column", sorted(contract.GENERATED_COLUMNS))
def test_generated_columns_are_blocked_by_ddl_not_by_privilege(conn: Any, column: str) -> None:
    """계산 컬럼 쓰기는 권한이 아니라 GENERATED 제약이 막는다.

    PostgreSQL 은 컬럼 권한을 보기 **전에** 파싱 단계에서 거부하므로 SQLSTATE 가
    42501(InsufficientPrivilege) 이 아니라 428C9(GeneratedAlways) 다. 방어선이
    두 겹이라는 뜻이며(DDL + GRANT 미부여), 어느 쪽이든 쓰기는 불가능하다.
    """
    with conn.cursor() as cur, pytest.raises(psycopg.errors.GeneratedAlways) as exc:
        # 식별자는 계약 상수에서만 오며 외부 입력이 아니다.
        cur.execute(f"UPDATE tn_crawl_target SET {column} = '7020'")  # noqa: S608
    assert exc.value.sqlstate == GENERATED_ALWAYS
    conn.rollback()


def test_generated_columns_also_lack_update_privilege(conn: Any, runtime_role: str) -> None:
    """두 번째 방어선: 권한 자체도 부여되어 있지 않다."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.column_privileges
             WHERE grantee = %s AND table_name = 'tn_crawl_target'
               AND privilege_type = 'UPDATE' AND column_name = ANY(%s)
            """,
            (runtime_role, list(contract.GENERATED_COLUMNS)),
        )
        assert cur.fetchall() == []
