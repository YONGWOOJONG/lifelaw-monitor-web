"""인증 엔드포인트 — 화면 S-01 로그인, S-02 재인증.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.4 §18 §19
      DESIGN_admin_screen_inventory_v0_1.md S-01 S-02
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from lifelaw_web.api import security
from lifelaw_web.api.security import AuthError, RequestContext
from lifelaw_web.audit import writer
from lifelaw_web.auth import login as login_service
from lifelaw_web.auth import sessions
from lifelaw_web.dto.auth import (
    LoginRequest,
    LoginResponse,
    PrincipalResponse,
    ReauthRequest,
    SessionInfo,
)
from lifelaw_web.rbac import guard
from lifelaw_web.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _settings(request: Request) -> Settings:
    from lifelaw_web.api.app import get_settings

    return get_settings(request)


def _db(request: Request) -> Iterator[Any]:
    from lifelaw_web.api.app import db

    with db(_settings(request)) as conn:
        yield conn


def _set_session_cookie(
    response: Response, settings: Settings, issued: sessions.IssuedSession
) -> None:
    cfg = settings.config.session
    response.set_cookie(
        key=cfg.cookie_name,
        value=issued.session_token,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
        path="/",
        # 쿠키 만료를 절대 만료와 맞춘다. 유휴 만료는 서버가 판정한다.
        max_age=cfg.absolute_hours * 3600,
    )


def _principal_response(
    principal: guard.Principal, session: sessions.SessionContext, settings: Settings
) -> PrincipalResponse:
    return PrincipalResponse(
        user_id=principal.user_id,
        login_id=principal.login_id,
        user_nm=principal.user_nm,
        roles=sorted(principal.roles),
        permissions=sorted(principal.granted),
        session=SessionInfo(
            absolute_expires_at=session.absolute_expires_at.isoformat(),
            reauth_fresh=session.reauth_is_fresh(
                security.now_utc(), settings.config.session.reauth_valid_minutes
            ),
        ),
        # 세션에서 다시 계산한다. 저장된 값을 읽는 것이 아니다.
        csrf_token=sessions.csrf_for(
            session.session_token_hash, settings.secrets.session_secret
        ),
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    conn: Annotated[Any, Depends(_db)],
) -> LoginResponse:
    """로그인.

    CSRF 토큰 검사는 하지 않는다 — 아직 세션이 없어 토큰이 존재하지 않는다.
    대신 Origin 을 검증하고 SameSite 쿠키에 의존한다. 로그인 CSRF 는 세션
    탈취가 아니라 "공격자 계정으로 로그인시키기"라 위험 등급이 다르다.
    """
    settings = _settings(request)
    security.check_origin(request, settings)

    now = security.now_utc()
    source_ip = security.client_ip(request)
    agent = security.user_agent(request)
    cfg = settings.config.session

    result = login_service.authenticate(
        conn,
        login_id=payload.login_id,
        password=payload.password,
        max_failed=cfg.max_failed_logins,
        lockout_minutes=cfg.lockout_minutes,
        now=now,
    )

    if not result.ok:
        # 실패한 시도도 반드시 남긴다(설계 §19.1).
        writer.record(
            conn,
            actor=result.login_id or payload.login_id,
            action="LOGIN",
            result_cd=writer.RESULT_DENIED,
            source_ip=source_ip,
            user_agent=agent,
            target_type="TW_USER",
            target_id=str(result.user_id) if result.user_id else None,
            after_value={"outcome": result.outcome.value},
            reason="로그인 실패",
        )
        # **명시적으로 커밋한다.** 아래 예외는 요청 트랜잭션을 롤백시키는데,
        # 그러면 감사 기록과 실패 횟수 증가가 함께 사라진다. 실패한 시도를
        # 남기라는 §19.1 요구와 무차별 대입 잠금이 둘 다 무력화된다.
        conn.commit()
        # 실패 사유를 응답으로 구분해 주지 않는다. 계정 존재 여부가 새어나간다.
        raise AuthError("INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.")

    assert result.user_id is not None  # noqa: S101 - 성공 경로 불변식
    issued = sessions.create_session(
        conn,
        user_id=result.user_id,
        absolute_hours=cfg.absolute_hours,
        source_ip=source_ip,
        user_agent=agent,
        now=now,
        session_secret=settings.secrets.session_secret,
    )
    principal = guard.load_principal(
        conn,
        user_id=result.user_id,
        login_id=result.login_id or payload.login_id,
        user_nm=result.user_nm or "",
    )
    session = sessions.SessionContext(
        session_token_hash="",
        user_id=principal.user_id,
        login_id=principal.login_id,
        user_nm=principal.user_nm,
        csrf_token_hash="",
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=issued.absolute_expires_at,
        reauth_at=None,
    )

    writer.record(
        conn,
        actor=principal.login_id,
        actor_role_cd=principal.primary_role,
        action="LOGIN",
        result_cd=writer.RESULT_SUCCESS,
        source_ip=source_ip,
        user_agent=agent,
        target_type="TW_USER",
        target_id=str(principal.user_id),
        after_value={"roles": sorted(principal.roles)},
    )

    _set_session_cookie(response, settings, issued)
    return LoginResponse(
        principal=_principal_response(principal, session, settings),
        csrf_token=issued.csrf_token,
    )


def _require(request: Request, conn: Any) -> RequestContext:
    return security.require_context(conn, request, _settings(request), now=security.now_utc())


@router.get("/me", response_model=PrincipalResponse)
def me(request: Request, conn: Annotated[Any, Depends(_db)]) -> PrincipalResponse:
    """현재 사용자. 권한은 매 요청 재조회한 값이다."""
    context = _require(request, conn)
    return _principal_response(context.principal, context.session, _settings(request))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, conn: Annotated[Any, Depends(_db)]) -> Response:
    """로그아웃. 서버 측 세션을 삭제해 즉시 무효화한다."""
    settings = _settings(request)
    context = _require(request, conn)

    sessions.revoke(conn, session_token_hash=context.session.session_token_hash)
    writer.record(
        conn,
        actor=context.principal.login_id,
        actor_role_cd=context.principal.primary_role,
        action="LOGOUT",
        result_cd=writer.RESULT_SUCCESS,
        source_ip=context.source_ip,
        user_agent=context.user_agent,
        target_type="TW_USER",
        target_id=str(context.principal.user_id),
    )
    response.delete_cookie(settings.config.session.cookie_name, path="/")
    response.status_code = 204
    return response


@router.post("/reauth", response_model=PrincipalResponse)
def reauth(
    payload: ReauthRequest, request: Request, conn: Annotated[Any, Depends(_db)]
) -> PrincipalResponse:
    """재인증. 최고 위험 작업 전에 비밀번호를 다시 확인한다(설계 §18).

    세션 재사용으로 대체하지 않는다.
    """
    settings = _settings(request)
    context = _require(request, conn)
    now = security.now_utc()

    if not login_service.verify_current_password(
        conn, user_id=context.principal.user_id, password=payload.password
    ):
        writer.record(
            conn,
            actor=context.principal.login_id,
            actor_role_cd=context.principal.primary_role,
            action="REAUTH",
            result_cd=writer.RESULT_DENIED,
            source_ip=context.source_ip,
            user_agent=context.user_agent,
            target_type="TW_USER",
            target_id=str(context.principal.user_id),
        )
        # 로그인 실패와 같은 이유로 명시적 커밋이 필요하다.
        conn.commit()
        raise AuthError("REAUTH_FAILED", "비밀번호가 올바르지 않습니다.")

    sessions.mark_reauth(
        conn, session_token_hash=context.session.session_token_hash, now=now
    )
    writer.record(
        conn,
        actor=context.principal.login_id,
        actor_role_cd=context.principal.primary_role,
        action="REAUTH",
        result_cd=writer.RESULT_SUCCESS,
        source_ip=context.source_ip,
        user_agent=context.user_agent,
        target_type="TW_USER",
        target_id=str(context.principal.user_id),
    )

    refreshed = sessions.SessionContext(
        session_token_hash=context.session.session_token_hash,
        user_id=context.session.user_id,
        login_id=context.session.login_id,
        user_nm=context.session.user_nm,
        csrf_token_hash=context.session.csrf_token_hash,
        created_at=context.session.created_at,
        last_seen_at=context.session.last_seen_at,
        absolute_expires_at=context.session.absolute_expires_at,
        reauth_at=now,
    )
    return _principal_response(context.principal, refreshed, settings)
