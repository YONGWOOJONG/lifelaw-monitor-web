"""조회 API — 화면 S-03, S-04, S-05, S-06, S-10, S-11, S-16, S-17.

권위: DESIGN_admin_screen_inventory_v0_1.md
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3

전부 읽기 전용이다. 상태 변경 경로를 두지 않는다. 권한은 화면-권한 매트릭스를
따르며, 인가는 매 요청 서버에서 검증한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from lifelaw_web.api import security
from lifelaw_web.api.security import RequestContext
from lifelaw_web.dto.read import (
    BatchRunDetail,
    BatchRunPage,
    CommonCodeList,
    CountResponse,
    DashboardResponse,
    HistoryPage,
    LinkPage,
    SitePolicyList,
    TargetDetail,
    TargetPage,
)
from lifelaw_web.query import batches, dashboard, reference, retention
from lifelaw_web.query import targets as targets_query
from lifelaw_web.query.paging import DEFAULT_LIMIT, MAX_LIMIT, PageParams, SortError
from lifelaw_web.rbac import permissions
from lifelaw_web.settings import Settings

router = APIRouter(prefix="/api", tags=["read"])


def _settings(request: Request) -> Settings:
    from lifelaw_web.api.app import get_settings

    return get_settings(request)


def _db(request: Request) -> Iterator[Any]:
    from lifelaw_web.api.app import db

    with db(_settings(request)) as conn:
        yield conn


def _context(request: Request, conn: Any, permission: str) -> RequestContext:
    settings = _settings(request)
    context = security.require_context(conn, request, settings, now=security.now_utc())
    security.require_permission(context, permission, settings)
    return context


def _page_params(limit: int, offset: int) -> PageParams:
    return PageParams(limit=limit, offset=offset).normalised()


def _sorted_or_400(call: Any) -> Any:
    try:
        return call()
    except SortError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Offset = Annotated[int, Query(ge=0)]


# ---------------------------------------------------------------------------
# S-03 대시보드
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(request: Request, conn: Annotated[Any, Depends(_db)]) -> DashboardResponse:
    _context(request, conn, permissions.TARGET_READ)
    data = dashboard.build(conn)
    return DashboardResponse(
        batch_ymd=data.batch_ymd,
        total_targets=data.total_targets,
        crawl_stat=data.crawl_stat,
        extract_stat=data.extract_stat,
        norm_stat=data.norm_stat,
        cmpr_stat=data.cmpr_stat,
        change_yn=data.change_yn,
        change_detected_cnt=data.change_detected_cnt,
        baseline_cnt=data.baseline_cnt,
        failed_cnt=data.failed_cnt,
        excluded_cnt=data.excluded_cnt,
        diagnostic_cnt=data.diagnostic_cnt,
        latest_runs=[dict(r) for r in data.latest_runs],
    )


# ---------------------------------------------------------------------------
# S-04 대상 목록 / S-05 상세 / S-06 이력
# ---------------------------------------------------------------------------


def _target_filter(
    batch_ymd: str | None,
    site_host: str | None,
    link_class_cd: str | None,
    collect_target_kind_cd: str | None,
    crawl_stat_cd: str | None,
    extract_stat_cd: str | None,
    norm_stat_cd: str | None,
    cmpr_stat_cd: str | None,
    change_yn_cd: str | None,
    execution_collect_policy_cd: str | None,
    has_diagnostic: bool | None,
) -> targets_query.TargetFilter:
    return targets_query.TargetFilter(
        batch_ymd=batch_ymd,
        site_host=site_host,
        link_class_cd=link_class_cd,
        collect_target_kind_cd=collect_target_kind_cd,
        crawl_stat_cd=crawl_stat_cd,
        extract_stat_cd=extract_stat_cd,
        norm_stat_cd=norm_stat_cd,
        cmpr_stat_cd=cmpr_stat_cd,
        change_yn_cd=change_yn_cd,
        execution_collect_policy_cd=execution_collect_policy_cd,
        has_diagnostic=has_diagnostic,
    )


@router.get("/targets", response_model=TargetPage)
def list_targets(
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    sort: str | None = None,
    batch_ymd: str | None = None,
    site_host: str | None = None,
    link_class_cd: str | None = None,
    collect_target_kind_cd: str | None = None,
    crawl_stat_cd: str | None = None,
    extract_stat_cd: str | None = None,
    norm_stat_cd: str | None = None,
    cmpr_stat_cd: str | None = None,
    change_yn_cd: str | None = None,
    execution_collect_policy_cd: str | None = None,
    has_diagnostic: bool | None = None,
) -> TargetPage:
    """S-04. 각 행에 `target_policy_version` 을 함께 내려준다.

    전체 건수는 포함하지 않는다. 필요하면 `/targets/count` 를 따로 부른다.
    """
    _context(request, conn, permissions.TARGET_READ)
    filters = _target_filter(
        batch_ymd,
        site_host,
        link_class_cd,
        collect_target_kind_cd,
        crawl_stat_cd,
        extract_stat_cd,
        norm_stat_cd,
        cmpr_stat_cd,
        change_yn_cd,
        execution_collect_policy_cd,
        has_diagnostic,
    )
    page = _sorted_or_400(
        lambda: targets_query.list_targets(
            conn, filters=filters, params=_page_params(limit, offset), sort=sort
        )
    )
    return TargetPage(
        items=page.items, limit=page.limit, offset=page.offset, has_more=page.has_more
    )


@router.get("/targets/count", response_model=CountResponse)
def count_targets(
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    batch_ymd: str | None = None,
    site_host: str | None = None,
    link_class_cd: str | None = None,
    collect_target_kind_cd: str | None = None,
    crawl_stat_cd: str | None = None,
    extract_stat_cd: str | None = None,
    norm_stat_cd: str | None = None,
    cmpr_stat_cd: str | None = None,
    change_yn_cd: str | None = None,
    execution_collect_policy_cd: str | None = None,
    has_diagnostic: bool | None = None,
) -> CountResponse:
    """목록과 분리된 건수 조회(S-04). 대용량에서 매 요청 COUNT 를 피하기 위함이다."""
    _context(request, conn, permissions.TARGET_READ)
    filters = _target_filter(
        batch_ymd,
        site_host,
        link_class_cd,
        collect_target_kind_cd,
        crawl_stat_cd,
        extract_stat_cd,
        norm_stat_cd,
        cmpr_stat_cd,
        change_yn_cd,
        execution_collect_policy_cd,
        has_diagnostic,
    )
    return CountResponse(count=targets_query.count_targets(conn, filters=filters))


@router.get("/targets/{url_id}", response_model=TargetDetail)
def get_target(
    url_id: int, request: Request, conn: Annotated[Any, Depends(_db)]
) -> TargetDetail:
    """S-05. `crawl_candidate_url` 은 표시용이며 교체 경로를 제공하지 않는다."""
    _context(request, conn, permissions.TARGET_READ)
    row = targets_query.get_target(conn, url_id=url_id)
    if row is None:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    return TargetDetail(**row)


@router.get("/targets/{url_id}/history", response_model=HistoryPage)
def get_target_history(
    url_id: int,
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    batch_ymd_from: str | None = None,
) -> HistoryPage:
    """S-06.

    조회 가능 범위를 함께 내려준다. 범위 밖 조회의 0건은 **유실이 아니므로**
    화면이 둘을 구분해 표시해야 한다.
    """
    _context(request, conn, permissions.TARGET_HISTORY_READ)
    window = retention.available_window(conn)
    page = targets_query.list_history(
        conn,
        url_id=url_id,
        params=_page_params(limit, offset),
        batch_ymd_from=batch_ymd_from,
    )
    return HistoryPage(
        items=page.items,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
        available_months=list(window.months),
        min_batch_ymd=window.min_batch_ymd,
        max_batch_ymd=window.max_batch_ymd,
    )


# ---------------------------------------------------------------------------
# S-10 배치 원장 / S-11 상세
# ---------------------------------------------------------------------------


@router.get("/batch-runs", response_model=BatchRunPage)
def list_batch_runs(
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    sort: str | None = None,
    batch_ymd: str | None = None,
    run_mode: str | None = None,
    run_stat_cd: str | None = None,
) -> BatchRunPage:
    _context(request, conn, permissions.BATCH_READ)
    page = _sorted_or_400(
        lambda: batches.list_batch_runs(
            conn,
            batch_ymd=batch_ymd,
            run_mode=run_mode,
            run_stat_cd=run_stat_cd,
            params=_page_params(limit, offset),
            sort=sort,
        )
    )
    return BatchRunPage(
        items=page.items, limit=page.limit, offset=page.offset, has_more=page.has_more
    )


@router.get("/batch-runs/{run_id}", response_model=BatchRunDetail)
def get_batch_run(
    run_id: int, request: Request, conn: Annotated[Any, Depends(_db)]
) -> BatchRunDetail:
    _context(request, conn, permissions.BATCH_READ)
    row = batches.get_batch_run(conn, run_id=run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="배치 실행을 찾을 수 없습니다.")
    return BatchRunDetail(**row)


# ---------------------------------------------------------------------------
# S-16 R 마스터 / S-17 공통 코드 / 사이트 정책
# ---------------------------------------------------------------------------


@router.get("/links", response_model=LinkPage)
def list_links(
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    sort: str | None = None,
    con_link_class_cd: str | None = None,
) -> LinkPage:
    _context(request, conn, permissions.TARGET_READ)
    page = _sorted_or_400(
        lambda: reference.list_links(
            conn,
            con_link_class_cd=con_link_class_cd,
            params=_page_params(limit, offset),
            sort=sort,
        )
    )
    return LinkPage(
        items=page.items, limit=page.limit, offset=page.offset, has_more=page.has_more
    )


@router.get("/codes", response_model=CommonCodeList)
def list_codes(
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    code_grp_cd: str | None = None,
) -> CommonCodeList:
    """S-17. 읽기 전용이다. 편집 경로를 제공하지 않는다(설계 §14)."""
    _context(request, conn, permissions.TARGET_READ)
    return CommonCodeList(items=reference.list_common_codes(conn, code_grp_cd=code_grp_cd))


@router.get("/site-policies", response_model=SitePolicyList)
def list_site_policies(
    request: Request, conn: Annotated[Any, Depends(_db)]
) -> SitePolicyList:
    _context(request, conn, permissions.POLICY_READ)
    return SitePolicyList(items=reference.list_site_policies(conn))
