"""배치 실행 원장 조회 — 화면 S-10 목록, S-11 상세.

권위: DESIGN_admin_screen_inventory_v0_1.md S-10 S-11
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §11

Web 은 `TN_BATCH_RUN` 을 **읽기만** 한다. `run_mode` 와 `run_stat_cd` 를 쓰지
않는다. 실행 제어는 명령 Inbox(6단계) 소관이다.
"""

from __future__ import annotations

from typing import Any, Final

from psycopg import sql
from psycopg.rows import dict_row

from lifelaw_web.query.paging import (
    Page,
    PageParams,
    SortAllowlist,
    build_page,
    limit_offset,
    order_by,
    where_clause,
)

SORT_ALLOWLIST: Final[SortAllowlist] = {
    "batch_ymd": ("batch_ymd",),
    "run_id": ("run_id",),
    "started_at": ("started_at",),
    "run_stat": ("run_stat_cd",),
}
DEFAULT_SORT: Final = "-batch_ymd"

_COLUMNS: Final = sql.SQL("""
    run_id, batch_ymd, run_mode, run_stat_cd,
    started_at, ended_at,
    total_cnt, success_cnt, fail_cnt, change_detected_cnt,
    err_cnt, excluded_cnt, reg_dt
""")

_FILTER_COLUMNS: Final[dict[str, str]] = {
    "batch_ymd": "batch_ymd",
    "run_mode": "run_mode",
    "run_stat_cd": "run_stat_cd",
}


def list_batch_runs(
    conn: Any,
    *,
    batch_ymd: str | None,
    run_mode: str | None,
    run_stat_cd: str | None,
    params: PageParams,
    sort: str | None,
) -> Page[dict[str, Any]]:
    page = params.normalised()
    supplied = {"batch_ymd": batch_ymd, "run_mode": run_mode, "run_stat_cd": run_stat_cd}

    conditions: list[sql.Composable] = []
    values: list[Any] = []
    for field_name, column in _FILTER_COLUMNS.items():
        value = supplied[field_name]
        if value is None:
            continue
        conditions.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
        values.append(value)

    statement = (
        sql.SQL("SELECT ")
        + _COLUMNS
        + sql.SQL(" FROM tn_batch_run")
        + where_clause(conditions)
        + sql.SQL(" ORDER BY ")
        + order_by(sort, SORT_ALLOWLIST, DEFAULT_SORT)
        + sql.SQL(", run_id DESC")
        + limit_offset()
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, [*values, page.limit + 1, page.offset])
        rows = list(cur.fetchall())
    return build_page(rows, page)


def get_batch_run(conn: Any, *, run_id: int) -> dict[str, Any] | None:
    statement = (
        sql.SQL("SELECT ") + _COLUMNS + sql.SQL(" FROM tn_batch_run WHERE run_id = %s")
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, (run_id,))
        row = cur.fetchone()
    return dict(row) if row else None
