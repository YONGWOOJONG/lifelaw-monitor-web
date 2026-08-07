"""조회 응답 DTO.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §6
      DESIGN_admin_screen_inventory_v0_1.md

모델 객체를 그대로 노출하지 않는다. 조회 응답은 행 dict 를 그대로 담되,
**페이지 봉투(limit/offset/has_more)와 조회 가능 범위**를 명시적 필드로 둔다.
행 스키마를 DTO 로 다시 못 박지 않는 이유는 컬럼 계약의 단일 출처가
`docs/contracts/db-contract.md` 이기 때문이다 — 여기서 다시 선언하면 C-1 과
같은 이중 정의 드리프트가 생긴다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CountResponse(_Base):
    count: int


class _PageEnvelope(_Base):
    limit: int
    offset: int
    has_more: bool


class TargetPage(_PageEnvelope):
    items: list[dict[str, Any]]


class TargetDetail(_Base):
    """S-05. 추가 컬럼이 늘어도 계약 문서가 단일 출처다."""

    model_config = ConfigDict(extra="allow")


class HistoryPage(_PageEnvelope):
    items: list[dict[str, Any]]
    # 조회 가능 범위. 범위 밖의 0건은 유실이 아니다(S-06, D-30).
    available_months: list[str]
    min_batch_ymd: str | None
    max_batch_ymd: str | None


class BatchRunPage(_PageEnvelope):
    items: list[dict[str, Any]]


class BatchRunDetail(_Base):
    model_config = ConfigDict(extra="allow")


class LinkPage(_PageEnvelope):
    items: list[dict[str, Any]]


class CommonCodeList(_Base):
    items: list[dict[str, Any]]


class SitePolicyList(_Base):
    items: list[dict[str, Any]]


class DashboardResponse(_Base):
    batch_ymd: str | None
    total_targets: int
    crawl_stat: dict[str, int]
    extract_stat: dict[str, int]
    norm_stat: dict[str, int]
    cmpr_stat: dict[str, int]
    change_yn: dict[str, int]
    # 5001(기준선 설정)은 change_detected_cnt 에 **포함되지 않는다**.
    # 별도 필드로 분리해 화면이 둘을 섞지 못하게 한다.
    change_detected_cnt: int
    baseline_cnt: int
    failed_cnt: int
    excluded_cnt: int
    diagnostic_cnt: int
    latest_runs: list[dict[str, Any]]
