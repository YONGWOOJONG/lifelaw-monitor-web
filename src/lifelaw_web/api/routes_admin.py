"""관리 화면 API — S-18 사용자, S-19 역할·권한, S-20 감사 로그.

권위: DESIGN_admin_screen_inventory_v0_1.md S-18 S-19 S-20
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17 §18 §19 §20

이 파일은 저장소에서 **처음으로 계정·권한을 바꾸는 경로**다. 그래서 모든
쓰기 핸들러가 같은 골격을 따른다.

  1. `_context(...)` — 세션·CSRF·Origin·권한·재인증을 한 번에 통과시킨다.
     `user:manage` 는 `PERMISSIONS_REQUIRING_REAUTH` 에 있어 재인증 신선도까지
     여기서 걸린다(§18 최고 등급).
  2. 사유(`reason`)를 DTO 가 필수로 받는다. §18 은 중위험 이상에 사유를 요구한다.
  3. 변경 **전 값을 먼저 읽는다.** 감사의 before 는 나중에 재구성할 수 없다.
  4. 실패도 감사에 남긴다(§19.1 "실패한 시도도 남긴다"). 거부 사유가 곧
     보안 신호이므로, 성공만 남기면 공격 시도가 통째로 안 보인다.

**4-eyes 승인은 이 판에 없다.** §18 은 계정 권한 변경에 승인을 요구하지만,
승인 **대기열**을 담을 표가 스키마에 없다(`TW_APPROVAL` 은 결정 원장이고,
`TW_ADMIN_COMMAND` 는 §9 상 수집기 명령 전용이다). 설계의 단계표도
S-18·S-19 를 2단계, 승인 대기함(S-15)을 6단계에 둔다. 그래서 이번 판은
권한 + 사유 + 재인증 + 감사까지 강제하고, 승인 흐름은 S-15 에서 붙인다.
마이그레이션 0002 가 `TW_APPROVAL` 에 `target_type`/`target_id` 를 열어두었으므로
그때 계정·정책 승인을 기록할 자리는 이미 있다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from lifelaw_web.api import security
from lifelaw_web.api.security import RequestContext
from lifelaw_web.audit import writer as audit
from lifelaw_web.dto.admin import (
    AuditActionList,
    AuditPage,
    PasswordResetRequest,
    PermissionList,
    RoleCreateRequest,
    RoleDeleteRequest,
    RoleList,
    RoleUpdateRequest,
    UnlockRequest,
    UserActiveRequest,
    UserCreateRequest,
    UserList,
    UserRolesRequest,
    UserUpdateRequest,
)
from lifelaw_web.query import accounts, audit_log, rbac_admin
from lifelaw_web.query.paging import DEFAULT_LIMIT, MAX_LIMIT, PageParams
from lifelaw_web.rbac import permissions
from lifelaw_web.settings import Settings

router = APIRouter(prefix="/api/admin", tags=["admin"])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Offset = Annotated[int, Query(ge=0)]


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


def _audit(
    conn: Any,
    context: RequestContext,
    request: Request,
    *,
    action: str,
    result_cd: str,
    target_type: str,
    target_id: str | None,
    reason: str,
    before: Any = None,
    after: Any = None,
) -> None:
    audit.record(
        conn,
        actor=context.principal.login_id,
        actor_role_cd=context.principal.primary_role,
        source_ip=security.client_ip(request),
        user_agent=request.headers.get("user-agent"),
        action=action,
        result_cd=result_cd,
        target_type=target_type,
        target_id=target_id,
        before_value=before,
        after_value=after,
        reason=reason,
    )


def _reject(
    conn: Any,
    context: RequestContext,
    request: Request,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    reason: str,
    message: str,
    status_code: int = 400,
    before: Any = None,
) -> HTTPException:
    """거부를 감사에 남기고 예외를 만들어 돌려준다.

    돌려주기만 하고 던지지 않는 이유는, 호출부에서 `raise _reject(...)` 로 써야
    "여기서 요청이 끝난다"가 눈에 보이기 때문이다.

    **감사를 명시적으로 커밋한다.** 호출부가 던지는 예외는 요청 트랜잭션을
    롤백시키고(`api/app.py` 의 `db()`), 그러면 방금 남긴 거부 기록까지 함께
    사라진다. §19.1 은 실패한 시도를 남기라고 요구한다 — 거부야말로 보안
    신호이므로 성공만 남으면 공격 시도가 통째로 안 보인다.
    `routes_auth` 의 로그인 실패 경로가 같은 이유로 같은 일을 한다.
    """
    _audit(
        conn,
        context,
        request,
        action=action,
        result_cd=audit.RESULT_DENIED,
        target_type=target_type,
        target_id=target_id,
        reason=f"{reason} / 거부: {message}",
        before=before,
    )
    conn.commit()
    return HTTPException(status_code=status_code, detail=message)


# ---------------------------------------------------------------------------
# S-19 역할·권한
# ---------------------------------------------------------------------------


@router.get("/permissions", response_model=PermissionList)
def get_permissions(request: Request, conn: Annotated[Any, Depends(_db)]) -> PermissionList:
    _context(request, conn, permissions.USER_MANAGE)
    return PermissionList(items=rbac_admin.list_permissions(conn))


@router.get("/roles", response_model=RoleList)
def get_roles(request: Request, conn: Annotated[Any, Depends(_db)]) -> RoleList:
    _context(request, conn, permissions.USER_MANAGE)
    return RoleList(items=rbac_admin.list_roles(conn))


@router.post("/roles", response_model=RoleList, status_code=201)
def post_role(
    body: RoleCreateRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> RoleList:
    context = _context(request, conn, permissions.USER_MANAGE)
    try:
        created = rbac_admin.create_role(
            conn,
            role_cd=body.role_cd,
            role_nm=body.role_nm,
            role_desc=body.role_desc,
            perm_cds=body.permissions,
        )
    except rbac_admin.RbacError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="ROLE_CREATE",
            target_type="ROLE",
            target_id=body.role_cd,
            reason=body.reason,
            message=str(exc),
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="ROLE_CREATE",
        result_cd=audit.RESULT_SUCCESS,
        target_type="ROLE",
        target_id=created["role_cd"],
        reason=body.reason,
        after=created,
    )
    return RoleList(items=rbac_admin.list_roles(conn))


@router.put("/roles/{role_cd}", response_model=RoleList)
def put_role(
    role_cd: str, body: RoleUpdateRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> RoleList:
    context = _context(request, conn, permissions.USER_MANAGE)
    before = rbac_admin.get_role(conn, role_cd)
    try:
        rbac_admin.update_role(
            conn,
            role_cd=role_cd,
            role_nm=body.role_nm,
            role_desc=body.role_desc,
            perm_cds=body.permissions,
            expected={
                "role_nm": body.expected_role_nm,
                "permissions": body.expected_permissions,
            },
        )
    except rbac_admin.VersionConflictError as exc:
        _audit(
            conn,
            context,
            request,
            action="ROLE_UPDATE",
            result_cd=audit.RESULT_DENIED,
            target_type="ROLE",
            target_id=role_cd,
            reason=f"{body.reason} / 거부: 낙관적 잠금 충돌",
            before=before,
        )
        conn.commit()  # 아래 예외가 롤백시키기 전에 감사를 확정한다. `_reject` 주석 참조.
        # 409 에 현재 값을 동봉한다. 화면은 조용히 재시도하지 않고 차이를 보여준다.
        raise HTTPException(
            status_code=409, detail={"message": exc.message, "current": exc.current}
        ) from exc
    except rbac_admin.RbacError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="ROLE_UPDATE",
            target_type="ROLE",
            target_id=role_cd,
            reason=body.reason,
            message=str(exc),
            before=before,
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="ROLE_UPDATE",
        result_cd=audit.RESULT_SUCCESS,
        target_type="ROLE",
        target_id=role_cd,
        reason=body.reason,
        before=before,
        after=rbac_admin.get_role(conn, role_cd),
    )
    return RoleList(items=rbac_admin.list_roles(conn))


@router.delete("/roles/{role_cd}", response_model=RoleList)
def delete_role(
    role_cd: str, body: RoleDeleteRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> RoleList:
    """역할 삭제. 저장소에서 진짜 DELETE 가 허용된 유일한 경로다."""
    context = _context(request, conn, permissions.USER_MANAGE)
    try:
        removed = rbac_admin.delete_role(conn, role_cd=role_cd)
    except rbac_admin.RbacError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="ROLE_DELETE",
            target_type="ROLE",
            target_id=role_cd,
            reason=body.reason,
            message=str(exc),
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="ROLE_DELETE",
        result_cd=audit.RESULT_SUCCESS,
        target_type="ROLE",
        target_id=role_cd,
        reason=body.reason,
        before=removed,
    )
    return RoleList(items=rbac_admin.list_roles(conn))


# ---------------------------------------------------------------------------
# S-18 사용자
# ---------------------------------------------------------------------------


@router.get("/users", response_model=UserList)
def get_users(request: Request, conn: Annotated[Any, Depends(_db)]) -> UserList:
    _context(request, conn, permissions.USER_MANAGE)
    return UserList(items=accounts.list_users(conn))


@router.post("/users", response_model=UserList, status_code=201)
def post_user(
    body: UserCreateRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> UserList:
    context = _context(request, conn, permissions.USER_MANAGE)
    try:
        created = accounts.create_user(
            conn,
            login_id=body.login_id,
            user_nm=body.user_nm,
            password=body.password,
            role_cds=body.roles,
            actor=context.principal.login_id,
        )
    except accounts.AccountError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="USER_CREATE",
            target_type="USER",
            target_id=body.login_id,
            reason=body.reason,
            message=str(exc),
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="USER_CREATE",
        result_cd=audit.RESULT_SUCCESS,
        target_type="USER",
        target_id=str(created["user_id"]),
        reason=body.reason,
        after=created,
    )
    return UserList(items=accounts.list_users(conn))


@router.put("/users/{user_id}", response_model=UserList)
def put_user(
    user_id: int, body: UserUpdateRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> UserList:
    context = _context(request, conn, permissions.USER_MANAGE)
    before = accounts.get_user(conn, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    try:
        after = accounts.update_user(
            conn,
            user_id=user_id,
            user_nm=body.user_nm,
            actor=context.principal.login_id,
            current=before,
        )
    except accounts.AccountError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="USER_UPDATE",
            target_type="USER",
            target_id=str(user_id),
            reason=body.reason,
            message=str(exc),
            before=before,
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="USER_UPDATE",
        result_cd=audit.RESULT_SUCCESS,
        target_type="USER",
        target_id=str(user_id),
        reason=body.reason,
        before=before,
        after=after,
    )
    return UserList(items=accounts.list_users(conn))


@router.put("/users/{user_id}/roles", response_model=UserList)
def put_user_roles(
    user_id: int, body: UserRolesRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> UserList:
    """계정 권한 변경 — §18 최고 위험. 재인증은 `_context` 가 이미 걸었다."""
    context = _context(request, conn, permissions.USER_MANAGE)
    before = accounts.get_user(conn, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if sorted(before["roles"]) != sorted(body.expected_roles):
        _audit(
            conn,
            context,
            request,
            action="USER_ROLES",
            result_cd=audit.RESULT_DENIED,
            target_type="USER",
            target_id=str(user_id),
            reason=f"{body.reason} / 거부: 낙관적 잠금 충돌",
            before=before,
        )
        conn.commit()  # 아래 예외가 롤백시키기 전에 감사를 확정한다. `_reject` 주석 참조.
        raise HTTPException(
            status_code=409,
            detail={
                "message": "다른 사용자가 이 계정의 역할을 먼저 변경했습니다.",
                "current": before,
            },
        )

    try:
        after = accounts.set_roles(
            conn,
            user_id=user_id,
            role_cds=body.roles,
            actor=context.principal.login_id,
            acting_user_id=context.principal.user_id,
        )
    except accounts.AccountError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="USER_ROLES",
            target_type="USER",
            target_id=str(user_id),
            reason=body.reason,
            message=str(exc),
            before=before,
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="USER_ROLES",
        result_cd=audit.RESULT_SUCCESS,
        target_type="USER",
        target_id=str(user_id),
        reason=body.reason,
        before=before,
        after=after,
    )
    return UserList(items=accounts.list_users(conn))


@router.put("/users/{user_id}/active", response_model=UserList)
def put_user_active(
    user_id: int, body: UserActiveRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> UserList:
    context = _context(request, conn, permissions.USER_MANAGE)
    before = accounts.get_user(conn, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    try:
        after = accounts.set_active(
            conn,
            user_id=user_id,
            active=body.active,
            actor=context.principal.login_id,
            acting_user_id=context.principal.user_id,
        )
    except accounts.AccountError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="USER_ACTIVE",
            target_type="USER",
            target_id=str(user_id),
            reason=body.reason,
            message=str(exc),
            before=before,
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="USER_ACTIVE",
        result_cd=audit.RESULT_SUCCESS,
        target_type="USER",
        target_id=str(user_id),
        reason=body.reason,
        before=before,
        after=after,
    )
    return UserList(items=accounts.list_users(conn))


@router.put("/users/{user_id}/password", response_model=UserList)
def put_user_password(
    user_id: int, body: PasswordResetRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> UserList:
    """비밀번호 재설정.

    감사에 before/after 를 남기되 **비밀번호는 담지 않는다.** `accounts` 가
    돌려주는 행에 해시가 없고, 여기서도 `body.password` 를 만지지 않는다.
    """
    context = _context(request, conn, permissions.USER_MANAGE)
    before = accounts.get_user(conn, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    try:
        accounts.reset_password(
            conn, user_id=user_id, password=body.password, actor=context.principal.login_id
        )
    except accounts.AccountError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="USER_PASSWORD_RESET",
            target_type="USER",
            target_id=str(user_id),
            reason=body.reason,
            message=str(exc),
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="USER_PASSWORD_RESET",
        result_cd=audit.RESULT_SUCCESS,
        target_type="USER",
        target_id=str(user_id),
        reason=body.reason,
        after={"login_id": before["login_id"], "password": audit.MASK, "sessions_revoked": True},
    )
    return UserList(items=accounts.list_users(conn))


@router.put("/users/{user_id}/unlock", response_model=UserList)
def put_user_unlock(
    user_id: int, body: UnlockRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> UserList:
    context = _context(request, conn, permissions.USER_MANAGE)
    before = accounts.get_user(conn, user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    try:
        after = accounts.unlock(conn, user_id=user_id, actor=context.principal.login_id)
    except accounts.AccountError as exc:
        raise _reject(
            conn,
            context,
            request,
            action="USER_UNLOCK",
            target_type="USER",
            target_id=str(user_id),
            reason=body.reason,
            message=str(exc),
            before=before,
        ) from exc

    _audit(
        conn,
        context,
        request,
        action="USER_UNLOCK",
        result_cd=audit.RESULT_SUCCESS,
        target_type="USER",
        target_id=str(user_id),
        reason=body.reason,
        before=before,
        after=after,
    )
    return UserList(items=accounts.list_users(conn))


# ---------------------------------------------------------------------------
# S-20 감사 로그 — 읽기 전용
# ---------------------------------------------------------------------------


@router.get("/audit", response_model=AuditPage)
def get_audit(
    request: Request,
    conn: Annotated[Any, Depends(_db)],
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    result_cd: str | None = None,
    occurred_from: str | None = None,
    occurred_to: str | None = None,
) -> AuditPage:
    """S-20. `audit:read` 는 `user:manage` 와 별개 권한이다(AUDITOR 분리)."""
    _context(request, conn, permissions.AUDIT_READ)
    try:
        page = audit_log.list_entries(
            conn,
            params=PageParams(limit=limit, offset=offset).normalised(),
            actor=actor,
            action=action,
            target_type=target_type,
            result_cd=result_cd,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuditPage(
        items=page.items, limit=page.limit, offset=page.offset, has_more=page.has_more
    )


@router.get("/audit/actions", response_model=AuditActionList)
def get_audit_actions(request: Request, conn: Annotated[Any, Depends(_db)]) -> AuditActionList:
    _context(request, conn, permissions.AUDIT_READ)
    return AuditActionList(items=audit_log.list_actions(conn))
