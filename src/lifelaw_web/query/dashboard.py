"""운영 현황 집계 — 화면 S-03.

권위: DESIGN_admin_screen_inventory_v0_1.md S-03
      docs/contracts/db-contract.md §2.6

┌──────────────────────────────────────────────────────────────────────────┐
│ 집계 규칙 (중요)                                                          │
│                                                                          │
│ `5001`(기준선 설정)은 신규 등록·강제 재기준선·성공 기준선 부재를 포함한다. │
│ **변경 감지 건수에 합산하지 않는다.** 합산하면 신규 대상이 대량 등록된 날  │
│ 변경 건수가 폭증한 것처럼 보인다.                                         │
└──────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from psycopg import sql

from lifelaw_web.db import contract

# 변경 "감지"로 세는 코드. 5001 은 여기 없다.
CHANGE_DETECTED_CODES: Final[tuple[str, ...]] = ("5020", "5040")
BASELINE_CODE: Final = contract.CHANGE_BASELINE_CODE  # "5001"


@dataclass(frozen=True)
class Dashboard:
    batch_ymd: str | None
    total_targets: int
    crawl_stat: dict[str, int] = field(default_factory=dict)
    extract_stat: dict[str, int] = field(default_factory=dict)
    norm_stat: dict[str, int] = field(default_factory=dict)
    cmpr_stat: dict[str, int] = field(default_factory=dict)
    change_yn: dict[str, int] = field(default_factory=dict)
    change_detected_cnt: int = 0
    baseline_cnt: int = 0
    failed_cnt: int = 0
    excluded_cnt: int = 0
    diagnostic_cnt: int = 0
    latest_runs: list[dict[str, Any]] = field(default_factory=list)


# 집계 대상 상태 컬럼. 이 표의 값만 식별자로 SQL 에 들어간다.
_TALLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"crawl_stat_cd", "extract_stat_cd", "norm_stat_cd", "cmpr_stat_cd", "change_yn_cd"}
)


def _tally(conn: Any, column: str) -> dict[str, int]:
    """상태 코드 분포. 컬럼명은 allowlist 를 거쳐 Identifier 로만 합성한다."""
    if column not in _TALLY_COLUMNS:
        raise ValueError(f"집계 대상 컬럼이 아닙니다: {column}")
    statement = sql.SQL("SELECT {}, count(*) FROM tn_crawl_target GROUP BY 1").format(
        sql.Identifier(column)
    )
    with conn.cursor() as cur:
        cur.execute(statement)
        return {str(r[0]): int(r[1]) for r in cur.fetchall()}


def build(conn: Any) -> Dashboard:
    from psycopg.rows import dict_row

    with conn.cursor() as cur:
        cur.execute("SELECT count(*), max(batch_ymd) FROM tn_crawl_target")
        row = cur.fetchone()
        total = int(row[0]) if row else 0
        batch_ymd = str(row[1]) if row and row[1] else None

    change_yn = _tally(conn, "change_yn_cd")
    crawl_stat = _tally(conn, "crawl_stat_cd")

    # 변경 감지 = 5020 + 5040. 5001 은 더하지 않는다.
    change_detected = sum(change_yn.get(code, 0) for code in CHANGE_DETECTED_CODES)
    baseline = change_yn.get(BASELINE_CODE, 0)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE execution_collect_policy_cd = '7020'),
                   count(*) FILTER (WHERE crawl_diag_cd IS NOT NULL)
              FROM tn_crawl_target
            """
        )
        row = cur.fetchone()
        excluded = int(row[0]) if row else 0
        diagnostics = int(row[1]) if row else 0

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT run_id, batch_ymd, run_mode, run_stat_cd,
                   started_at, ended_at, total_cnt, change_detected_cnt
              FROM tn_batch_run
             ORDER BY batch_ymd DESC, run_id DESC
             LIMIT 5
            """
        )
        latest = [dict(r) for r in cur.fetchall()]

    failed = sum(
        crawl_stat.get(code, 0) for code in ("1090",)
    ) + sum(_tally(conn, "extract_stat_cd").get(code, 0) for code in ("2090",))

    return Dashboard(
        batch_ymd=batch_ymd,
        total_targets=total,
        crawl_stat=crawl_stat,
        extract_stat=_tally(conn, "extract_stat_cd"),
        norm_stat=_tally(conn, "norm_stat_cd"),
        cmpr_stat=_tally(conn, "cmpr_stat_cd"),
        change_yn=change_yn,
        change_detected_cnt=change_detected,
        baseline_cnt=baseline,
        failed_cnt=failed,
        excluded_cnt=excluded,
        diagnostic_cnt=diagnostics,
        latest_runs=latest,
    )
