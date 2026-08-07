"""참조 데이터 조회 — 화면 S-16 R 마스터, S-17 공통 코드.

권위: DESIGN_admin_screen_inventory_v0_1.md S-16 S-17
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §14

`TC_COMMON_CODE` 는 G1 정의의 물리화 사본이다. **읽기 전용**이며 추가·수정·
삭제·`use_yn` 토글 경로를 만들지 않는다. 라벨은 `code_nm` 을 쓰고 프론트엔드에
한글 라벨을 하드코딩하지 않는다.
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

LINK_SORT_ALLOWLIST: Final[SortAllowlist] = {
    "con_link_seq": ("l", "con_link_seq"),
    "con_link_nm": ("l", "con_link_nm"),
    "mod_dt": ("l", "mod_dt"),
}
LINK_DEFAULT_SORT: Final = "con_link_seq"


def list_common_codes(conn: Any, *, code_grp_cd: str | None = None) -> list[dict[str, Any]]:
    """공통 코드 전체. 34건 규모라 페이징하지 않는다."""
    conditions: list[sql.Composable] = [sql.SQL("use_yn = 'Y'")]
    values: list[Any] = []
    if code_grp_cd is not None:
        conditions.append(sql.SQL("code_grp_cd = %s"))
        values.append(code_grp_cd)

    statement = (
        sql.SQL(
            "SELECT code_grp_cd, code_val, code_nm, code_const, sort_ord FROM tc_common_code"
        )
        + where_clause(conditions)
        + sql.SQL(" ORDER BY code_grp_cd, sort_ord, code_val")
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, values)
        return [dict(r) for r in cur.fetchall()]


def list_links(
    conn: Any,
    *,
    con_link_class_cd: str | None,
    params: PageParams,
    sort: str | None,
) -> Page[dict[str, Any]]:
    """S-16 R 마스터 사본. R1 동기화가 유일한 작성자이므로 읽기만 한다."""
    page = params.normalised()
    conditions: list[sql.Composable] = []
    values: list[Any] = []
    if con_link_class_cd is not None:
        conditions.append(sql.SQL("l.con_link_class_cd = %s"))
        values.append(con_link_class_cd)

    statement = (
        sql.SQL("""
            SELECT l.con_link_seq, l.con_link_nm, l.con_link_class_cd,
                   l.con_link_url, l.fl_seq, l.lk_insp_dt, l.reg_dt, l.mod_dt,
                   t.url_id
              FROM tn_cnpcls_cnlnk l
              LEFT JOIN tn_crawl_target t ON t.con_link_seq = l.con_link_seq
        """)
        + where_clause(conditions)
        + sql.SQL(" ORDER BY ")
        + order_by(sort, LINK_SORT_ALLOWLIST, LINK_DEFAULT_SORT)
        + limit_offset()
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, [*values, page.limit + 1, page.offset])
        rows = list(cur.fetchall())
    return build_page(rows, page)


def list_site_policies(conn: Any) -> list[dict[str, Any]]:
    """사이트 정책 목록. S-04 필터의 host 선택지이기도 하다."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT p.site_policy_id, p.site_host, p.collect_policy_cd,
                   p.policy_version, p.policy_reason, p.moder, p.mod_dt,
                   (SELECT count(*) FROM tn_crawl_target t
                     WHERE t.site_policy_id = p.site_policy_id) AS target_cnt
              FROM tn_collect_site_policy p
             ORDER BY p.site_host
            """
        )
        return [dict(r) for r in cur.fetchall()]
