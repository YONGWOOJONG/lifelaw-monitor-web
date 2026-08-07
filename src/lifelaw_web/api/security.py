"""요청 단위 인증·인가·CSRF.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3 §17.4

§17.4 가 SPA + 쿠키 세션에 대해 강제한 조항을 여기서 구현한다.

  1. 동일 출처 배포 — CORS 미들웨어를 붙이지 않는다(교차 출처 자격증명 불가)
  2. 상태 변경 요청은 CSRF 토큰을 요구하고 Origin 을 검증한다
  3. 인증 상태를 프론트엔드가 판단하지 않는다 — 권한은 매 요청 재조회
  4. 401 과 403 을 구분한다
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import Request

from lifelaw_web.auth import sessions
from lifelaw_web.auth.sessions import SessionContext
from lifelaw_web.rbac import guard
from lifelaw_web.rbac.guard import Principal
from lifelaw_web.settings import Settings

CSRF_HEADER: Final = "X-CSRF-Token"
STATE_CHANGING_METHODS: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuthError(Exception):
    """인증 실패 → 401. 재로그인이 필요한 상태."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class CsrfError(Exception):
    """CSRF 검증 실패 → 403."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class RequestContext:
    principal: Principal
    session: SessionContext
    source_ip: str | None
    user_agent: str | None


def now_utc() -> datetime:
    return datetime.now(UTC)


def client_ip(request: Request) -> str | None:
    """클라이언트 IP.

    프록시 헤더(X-Forwarded-For)를 **신뢰하지 않는다.** 위조 가능하며, 신뢰
    경계는 배포 형상이 확정된 뒤에 정해야 한다(툴체인 T-3). 그전까지는 소켓
    주소만 쓴다.
    """
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def check_origin(request: Request, settings: Settings) -> None:
    """상태 변경 요청의 Origin 을 검증한다.

    Origin 헤더가 없으면(서버 간 호출, 테스트 클라이언트) 통과시킨다. 브라우저는
    교차 출처 상태 변경 요청에 Origin 을 항상 붙이므로, 없는 요청은 브라우저발
    CSRF 가 아니다. 그 경우에도 CSRF 토큰 검사는 그대로 적용된다.
    """
    if request.method not in STATE_CHANGING_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin not in settings.config.allowed_origins:
        raise CsrfError("허용되지 않은 Origin 입니다.")


def resolve_session_or_none(
    conn: Any, request: Request, settings: Settings, *, now: datetime
) -> SessionContext | None:
    token = request.cookies.get(settings.config.session.cookie_name)
    if not token:
        return None
    return sessions.resolve_session(
        conn,
        session_token=token,
        idle_minutes=settings.config.session.idle_minutes,
        now=now,
    )


def require_context(
    conn: Any, request: Request, settings: Settings, *, now: datetime
) -> RequestContext:
    """인증된 요청 컨텍스트를 만든다. CSRF 와 Origin 도 여기서 검증한다."""
    check_origin(request, settings)

    session = resolve_session_or_none(conn, request, settings, now=now)
    if session is None:
        raise AuthError("UNAUTHENTICATED", "로그인이 필요합니다.")

    if request.method in STATE_CHANGING_METHODS and not sessions.verify_csrf(
        session, request.headers.get(CSRF_HEADER)
    ):
        raise CsrfError("CSRF 토큰이 유효하지 않습니다.")

    # 권한은 매 요청 재조회한다. 로그인 시점 스냅샷을 쓰지 않는다.
    principal = guard.load_principal(
        conn,
        user_id=session.user_id,
        login_id=session.login_id,
        user_nm=session.user_nm,
    )
    return RequestContext(
        principal=principal,
        session=session,
        source_ip=client_ip(request),
        user_agent=user_agent(request),
    )


def require_permission(context: RequestContext, permission: str, settings: Settings) -> None:
    """권한을 확인하고, 최고 위험 권한이면 재인증 신선도까지 확인한다."""
    context.principal.require(permission)
    if guard.require_reauth_for(permission):
        fresh = context.session.reauth_is_fresh(
            now_utc(), settings.config.session.reauth_valid_minutes
        )
        if not fresh:
            raise guard.ReauthRequiredError(permission)
