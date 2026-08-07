"""계약·스키마 상태 — 화면 S-21.

권위: DESIGN_admin_screen_inventory_v0_1.md S-21
      docs/contracts/db-contract.md §3

이 화면은 조회 권한(`batch:read`)을 요구한다. 인증 없이 열지 않는다
(AGENTS.md §7 — 인증·인가를 모든 요청에서 검증).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from lifelaw_web.api import security
from lifelaw_web.db import contract
from lifelaw_web.db.schema_check import run_all
from lifelaw_web.rbac import permissions
from lifelaw_web.settings import Settings

router = APIRouter(prefix="/api/status", tags=["status"])


class CheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    title: str
    ok: bool
    informational: bool
    detail: str


class ContractPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    c1_version: str
    g1_version: str
    ddl_filename: str
    expected_migration: str


class ContractStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: ContractPin
    all_passed: bool
    failed_count: int
    checks: list[CheckItem]


def _settings(request: Request) -> Settings:
    from lifelaw_web.api.app import get_settings

    return get_settings(request)


def _db(request: Request) -> Iterator[Any]:
    from lifelaw_web.api.app import db

    with db(_settings(request)) as conn:
        yield conn


@router.get("/contract", response_model=ContractStatus)
def contract_status(request: Request, conn: Annotated[Any, Depends(_db)]) -> ContractStatus:
    settings = _settings(request)
    context = security.require_context(conn, request, settings, now=security.now_utc())
    security.require_permission(context, permissions.BATCH_READ, settings)

    results = run_all(conn, settings.secrets.db_user)
    failed = [r for r in results if not r.ok and not r.informational]
    return ContractStatus(
        pin=ContractPin(
            c1_version=contract.C1_DOC_VERSION,
            g1_version=contract.G1_DOC_VERSION,
            ddl_filename=contract.DDL_FILENAME,
            expected_migration=contract.EXPECTED_MIGRATION_VERSION,
        ),
        all_passed=not failed,
        failed_count=len(failed),
        checks=[
            CheckItem(
                check_id=r.check_id,
                title=r.title,
                ok=r.ok,
                informational=r.informational,
                detail=r.detail,
            )
            for r in results
        ],
    )
