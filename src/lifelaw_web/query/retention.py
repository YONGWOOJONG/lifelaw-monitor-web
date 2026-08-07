"""이력 조회 가능 범위.

권위: DESIGN_admin_screen_inventory_v0_1.md S-06
      docs/contracts/db-contract.md §1.2 §2.1

참조 저장소 D-30 은 `TH_CRAWL_TARGET` 을 **현재 업무월 + 직전 2개월**만 보존한다.
파티션이 없는 기간을 조회하면 0건이 나오는데, 이는 **유실이 아니다.** 화면이
"데이터 없음"과 "조회 범위 밖"을 구분할 수 있도록 실제 파티션 경계를 알려준다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

# th_crawl_target_2026_06 → 202606
_PARTITION_NAME = re.compile(r"^th_crawl_target_(\d{4})_(\d{2})$")

RETENTION_MONTHS: Final = 3


@dataclass(frozen=True)
class RetentionWindow:
    """실제로 조회 가능한 업무월 목록과 일자 경계."""

    months: tuple[str, ...]  # ("202606", "202607", "202608")
    min_batch_ymd: str | None
    max_batch_ymd: str | None

    @property
    def available(self) -> bool:
        return bool(self.months)


def available_window(conn: Any) -> RetentionWindow:
    """파티션 목록에서 조회 가능 범위를 도출한다.

    설정값이 아니라 **실제 파티션**을 읽는다. 문서상 3개월이라도 파티션이
    2개만 만들어져 있으면 조회 가능한 것은 2개월이다.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname
              FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid
             WHERE i.inhparent = 'th_crawl_target'::regclass
             ORDER BY c.relname
            """
        )
        names = [str(r[0]) for r in cur.fetchall()]

    months: list[str] = []
    for name in names:
        matched = _PARTITION_NAME.match(name)
        if matched:
            months.append(f"{matched.group(1)}{matched.group(2)}")
    months.sort()

    if not months:
        return RetentionWindow(months=(), min_batch_ymd=None, max_batch_ymd=None)

    return RetentionWindow(
        months=tuple(months),
        min_batch_ymd=f"{months[0]}01",
        max_batch_ymd=f"{months[-1]}31",
    )
