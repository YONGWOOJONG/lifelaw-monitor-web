"""수집 대상 조회 — 화면 S-04 목록, S-05 상세, S-06 이력.

권위: DESIGN_admin_screen_inventory_v0_1.md S-04 S-05 S-06
      docs/contracts/db-contract.md §2.2 §2.9

규칙:
  - 계산 컬럼(`effective`/`execution`)은 **읽어서 내려줄 뿐** 계산하지 않는다.
    프론트에서 OR 규칙을 재구현하면 수식이 바뀔 때 드리프트가 생긴다.
  - 각 행에 `target_policy_version` 을 함께 내려준다. S-09 일괄 변경의 입력이다.
  - `crawl_candidate_url` 은 표시용이다. "이 URL 로 교체" 경로를 만들지 않는다.
  - SQL 은 `psycopg.sql` 로 합성한다. f-string 보간을 쓰지 않는다(툴체인 §3).
"""

from __future__ import annotations

from dataclasses import dataclass
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
    "url_id": ("t", "url_id"),
    "batch_ymd": ("t", "batch_ymd"),
    "url": ("t", "con_link_url"),
    "crawl_stat": ("t", "crawl_stat_cd"),
    "change_yn": ("t", "change_yn_cd"),
    "policy": ("t", "execution_collect_policy_cd"),
    "mod_dt": ("t", "mod_dt"),
}
DEFAULT_SORT: Final = "url_id"

_LIST_COLUMNS: Final = sql.SQL("""
    t.url_id, t.con_link_seq, t.con_link_url, t.link_class_cd,
    t.collect_target_kind_cd, t.site_policy_id, p.site_host,
    t.site_collect_policy_cd, t.target_collect_policy_cd,
    t.effective_collect_policy_cd, t.execution_collect_policy_cd,
    t.run_collect_policy_cd,
    t.site_policy_version, t.target_policy_version,
    t.batch_ymd, t.crawl_stat_cd, t.extract_stat_cd, t.norm_stat_cd,
    t.cmpr_stat_cd, t.change_yn_cd, t.crawl_diag_cd, t.mod_dt
""")

_FROM: Final = sql.SQL("""
    FROM tn_crawl_target t
    LEFT JOIN tn_collect_site_policy p ON p.site_policy_id = t.site_policy_id
""")


@dataclass(frozen=True)
class TargetFilter:
    """S-04 필터. 전부 선택 사항이며 값은 파라미터로만 전달된다."""

    batch_ymd: str | None = None
    site_host: str | None = None
    link_class_cd: str | None = None
    collect_target_kind_cd: str | None = None
    crawl_stat_cd: str | None = None
    extract_stat_cd: str | None = None
    norm_stat_cd: str | None = None
    cmpr_stat_cd: str | None = None
    change_yn_cd: str | None = None
    execution_collect_policy_cd: str | None = None
    has_diagnostic: bool | None = None
    url_id: int | None = None


# 필터 필드 → (테이블 별칭, 컬럼). 컬럼명은 이 표에서만 나온다.
_FILTER_COLUMNS: Final[dict[str, tuple[str, str]]] = {
    "batch_ymd": ("t", "batch_ymd"),
    "site_host": ("p", "site_host"),
    "link_class_cd": ("t", "link_class_cd"),
    "collect_target_kind_cd": ("t", "collect_target_kind_cd"),
    "crawl_stat_cd": ("t", "crawl_stat_cd"),
    "extract_stat_cd": ("t", "extract_stat_cd"),
    "norm_stat_cd": ("t", "norm_stat_cd"),
    "cmpr_stat_cd": ("t", "cmpr_stat_cd"),
    "change_yn_cd": ("t", "change_yn_cd"),
    "execution_collect_policy_cd": ("t", "execution_collect_policy_cd"),
    "url_id": ("t", "url_id"),
}


def _where(filters: TargetFilter) -> tuple[sql.Composable, list[Any]]:
    conditions: list[sql.Composable] = []
    values: list[Any] = []

    for field_name, column in _FILTER_COLUMNS.items():
        value = getattr(filters, field_name)
        if value is None:
            continue
        conditions.append(sql.SQL("{} = %s").format(sql.Identifier(*column)))
        values.append(value)

    if filters.has_diagnostic is not None:
        conditions.append(
            sql.SQL("t.crawl_diag_cd IS NOT NULL")
            if filters.has_diagnostic
            else sql.SQL("t.crawl_diag_cd IS NULL")
        )

    return where_clause(conditions), values


def list_targets(
    conn: Any, *, filters: TargetFilter, params: PageParams, sort: str | None
) -> Page[dict[str, Any]]:
    page = params.normalised()
    where, values = _where(filters)
    statement = (
        sql.SQL("SELECT ")
        + _LIST_COLUMNS
        + _FROM
        + where
        + sql.SQL(" ORDER BY ")
        + order_by(sort, SORT_ALLOWLIST, DEFAULT_SORT)
        + sql.SQL(", t.url_id ASC")
        + limit_offset()
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, [*values, page.limit + 1, page.offset])
        rows = list(cur.fetchall())
    return build_page(rows, page)


def count_targets(conn: Any, *, filters: TargetFilter) -> int:
    """전체 건수. 목록과 분리해 호출하는 것이 전제다(S-04)."""
    where, values = _where(filters)
    statement = sql.SQL("SELECT count(*) ") + _FROM + where
    with conn.cursor() as cur:
        cur.execute(statement, values)
        row = cur.fetchone()
    return int(row[0]) if row else 0


_DETAIL_SQL: Final = """
    SELECT t.url_id, t.con_link_seq, t.con_link_url, t.link_class_cd,
           t.collect_target_kind_cd, t.site_policy_id, p.site_host,
           t.site_collect_policy_cd, t.target_collect_policy_cd,
           t.effective_collect_policy_cd, t.execution_collect_policy_cd,
           t.run_collect_policy_cd, t.run_exclusion_site_policy_id,
           t.run_exclusion_site_policy_version,
           t.site_policy_version, t.target_policy_version,
           t.batch_ymd,
           t.crawl_stat_cd, t.crawl_err_msg,
           t.crawl_diag_cd, t.crawl_diag_msg, t.crawl_candidate_url,
           t.extract_stat_cd, t.extract_err_msg, t.extract_method_cd,
           t.norm_stat_cd, t.norm_err_msg,
           t.cmpr_stat_cd, t.cmpr_err_msg,
           t.change_yn_cd, t.change_err_msg,
           t.raw_html_hash, t.norm_html_hash, t.prev_raw_hash, t.prev_norm_hash,
           t.file_size, t.file_mtime, t.file_format_cd,
           t.reg_dt, t.mod_dt,
           l.con_link_nm
      FROM tn_crawl_target t
      LEFT JOIN tn_collect_site_policy p ON p.site_policy_id = t.site_policy_id
      LEFT JOIN tn_cnpcls_cnlnk l ON l.con_link_seq = t.con_link_seq
     WHERE t.url_id = %s
"""


def get_target(conn: Any, *, url_id: int) -> dict[str, Any] | None:
    """S-05 상세. 목록보다 많은 컬럼을 내려준다."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_DETAIL_SQL, (url_id,))
        row = cur.fetchone()
    return dict(row) if row else None


_HISTORY_COLUMNS: Final = sql.SQL("""
    h.url_id, h.batch_ymd, h.con_link_url, h.link_class_cd,
    h.site_collect_policy_cd, h.target_collect_policy_cd,
    h.effective_collect_policy_cd, h.run_collect_policy_cd,
    h.execution_collect_policy_cd,
    h.crawl_stat_cd, h.crawl_err_msg, h.crawl_diag_cd,
    h.extract_stat_cd, h.norm_stat_cd, h.cmpr_stat_cd, h.change_yn_cd,
    h.raw_html_hash, h.norm_html_hash, h.file_format_cd, h.snap_dt
""")


def list_history(
    conn: Any, *, url_id: int, params: PageParams, batch_ymd_from: str | None = None
) -> Page[dict[str, Any]]:
    """S-06 이력. 최신 업무일자부터 내려준다.

    보존 범위 밖 조회는 결과가 0건이 된다. 그것이 유실이 아님을 화면이 구분해
    보여줘야 하므로, 조회 가능 범위는 `retention.available_window()` 로 함께
    전달한다.
    """
    page = params.normalised()
    conditions: list[sql.Composable] = [sql.SQL("h.url_id = %s")]
    values: list[Any] = [url_id]
    if batch_ymd_from:
        conditions.append(sql.SQL("h.batch_ymd >= %s"))
        values.append(batch_ymd_from)

    statement = (
        sql.SQL("SELECT ")
        + _HISTORY_COLUMNS
        + sql.SQL(" FROM th_crawl_target h")
        + where_clause(conditions)
        + sql.SQL(" ORDER BY h.batch_ymd DESC")
        + limit_offset()
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, [*values, page.limit + 1, page.offset])
        rows = list(cur.fetchall())
    return build_page(rows, page)
