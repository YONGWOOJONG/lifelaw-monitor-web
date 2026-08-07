"""감사 로그 조회 — 화면 S-20.

권위: DESIGN_admin_screen_inventory_v0_1.md S-20 (쓰기 **없음**, `audit:read`)
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §15 §19.1

**읽기 전용이다.** `TW_AUDIT_LOG` 는 append-only 이며(§15) 런타임 롤에
UPDATE·DELETE 가 부여돼 있지 않다. 수정·삭제 경로를 만들지 않는다.

`before_value` / `after_value` 는 기록 시점에 이미 마스킹된 값이다
(`audit/writer.py`). 여기서 다시 가공하지 않고 그대로 내린다 — 조회 쪽에서
한 번 더 손대면 "무엇이 저장돼 있는가"와 "무엇이 보이는가"가 갈린다.
"""

from __future__ import annotations

from typing import Any, Final

from psycopg import sql
from psycopg.rows import dict_row

from lifelaw_web.query.paging import Page, PageParams, build_page, limit_offset

RESULT_CODES: Final[tuple[str, ...]] = ("SUCCESS", "DENIED", "FAILED", "TIMEOUT")


def list_entries(
    conn: Any,
    *,
    params: PageParams,
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    result_cd: str | None = None,
    occurred_from: str | None = None,
    occurred_to: str | None = None,
) -> Page[dict[str, Any]]:
    """감사 로그 페이지.

    정렬은 최신순 고정이다. 감사 로그를 오래된 순으로 보는 화면은 요구된 적이
    없고, 정렬 옵션을 열면 대용량 표에서 인덱스를 벗어나는 조합이 생긴다.
    """
    conditions: list[sql.Composable] = []
    values: list[Any] = []

    def add(fragment: str, value: Any) -> None:
        conditions.append(sql.SQL(fragment))
        values.append(value)

    if actor:
        add("actor ILIKE %s", f"%{actor}%")
    if action:
        add("action = %s", action)
    if target_type:
        add("target_type = %s", target_type)
    if result_cd:
        if result_cd not in RESULT_CODES:
            raise ValueError(f"알 수 없는 결과 코드입니다: {result_cd}")
        add("result_cd = %s", result_cd)
    if occurred_from:
        add("occurred_at >= %s", occurred_from)
    if occurred_to:
        add("occurred_at < %s", occurred_to)

    where = (
        sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("")
    )
    statement = (
        sql.SQL(
            """
            SELECT audit_id, occurred_at, actor, actor_role_cd, source_ip,
                   action, target_type, target_id,
                   before_value, after_value, reason,
                   approval_id, idempotency_key, result_cd
              FROM tw_audit_log
            """
        )
        + where
        + sql.SQL(" ORDER BY occurred_at DESC, audit_id DESC ")
        + limit_offset()
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, (*values, params.limit + 1, params.offset))
        rows = [dict(r) for r in cur.fetchall()]
    return build_page(rows, params)


def list_actions(conn: Any) -> list[str]:
    """기록된 적 있는 action 목록. 필터 드롭다운을 실제 값으로 채운다."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT action FROM tw_audit_log ORDER BY action")
        return [str(r[0]) for r in cur.fetchall()]
