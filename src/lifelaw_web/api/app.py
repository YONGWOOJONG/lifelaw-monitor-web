"""FastAPI 앱.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.4 §19 §21

기동 시 DB 계약을 fail-closed 로 검증한다. 실패하면 **기능을 열지 않는다.**
CORS 미들웨어를 붙이지 않는다 — 동일 출처 배포가 전제다(§17.4 강제 조항 1·2).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Final

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from lifelaw_web.api import security
from lifelaw_web.api.routes_admin import router as admin_router
from lifelaw_web.api.routes_auth import router as auth_router
from lifelaw_web.api.routes_read import router as read_router
from lifelaw_web.api.routes_status import router as status_router
from lifelaw_web.db.connection import connect
from lifelaw_web.db.schema_check import SchemaContractError, assert_contract
from lifelaw_web.rbac.guard import PermissionDeniedError, ReauthRequiredError
from lifelaw_web.settings import Settings, load_settings

logger = logging.getLogger("lifelaw_web.api")

STATE_SETTINGS: Final = "lifelaw_settings"


@contextmanager
def db(settings: Settings) -> Iterator[Any]:
    """요청 단위 트랜잭션. 예외가 나면 커밋하지 않는다."""
    with connect(settings) as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_settings(request: Request) -> Settings:
    settings: Settings = getattr(request.app.state, STATE_SETTINGS)
    return settings


def create_app(settings: Settings | None = None, *, verify_contract: bool = True) -> FastAPI:
    resolved = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if verify_contract:
            with connect(resolved) as conn:
                results = assert_contract(conn, resolved.secrets.db_user)
            logger.info("DB 계약 검증 통과 (%d건)", len(results))
        yield

    app = FastAPI(
        title="lifelaw-monitor-web admin API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    setattr(app.state, STATE_SETTINGS, resolved)

    # ── 예외 → 응답 매핑 ────────────────────────────────────────────────────
    #
    # 401 과 403 을 구분한다(설계 §17.4 강제 조항 5). SPA 가 403 을 401 로
    # 오인해 로그인 화면을 띄우면 사용자가 원인을 오해한다.

    @app.exception_handler(security.AuthError)
    async def _auth_error(request: Request, exc: security.AuthError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=401,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(security.CsrfError)
    async def _csrf_error(request: Request, exc: security.CsrfError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=403,
            content={"code": "CSRF_FAILED", "message": exc.message},
        )

    @app.exception_handler(PermissionDeniedError)
    async def _denied(request: Request, exc: PermissionDeniedError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=403,
            content={
                "code": "PERMISSION_DENIED",
                "message": "이 작업에 필요한 권한이 없습니다.",
                "required_permission": exc.required,
            },
        )

    @app.exception_handler(ReauthRequiredError)
    async def _reauth(request: Request, exc: ReauthRequiredError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=403,
            content={
                "code": "REAUTH_REQUIRED",
                "message": "고위험 작업입니다. 비밀번호를 다시 확인해 주세요.",
                "required_permission": exc.required,
            },
        )

    @app.exception_handler(SchemaContractError)
    async def _contract(request: Request, exc: SchemaContractError) -> JSONResponse:
        del request
        logger.error("DB 계약 불일치: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"code": "CONTRACT_MISMATCH", "message": "데이터 계약이 일치하지 않습니다."},
        )

    @app.exception_handler(psycopg.Error)
    async def _db_error(request: Request, exc: psycopg.Error) -> JSONResponse:
        del request
        # 오류 메시지에 내부 경로·DSN·스택트레이스를 노출하지 않는다(설계 §7).
        logger.error("DB 오류: %s sqlstate=%s", type(exc).__name__, exc.sqlstate)
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "요청을 처리하지 못했습니다."},
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(auth_router)
    app.include_router(status_router)
    app.include_router(read_router)
    app.include_router(admin_router)
    return app
