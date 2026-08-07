"""RBAC 단위 테스트 — default-deny 와 4-eyes.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17 (A-05 승인)
      DESIGN_admin_screen_inventory_v0_1.md §5

DB 를 쓰지 않는다.
"""

from __future__ import annotations

import pytest

from lifelaw_web.rbac import permissions
from lifelaw_web.rbac.guard import PermissionDeniedError, Principal


def principal(*granted: str, roles: tuple[str, ...] = ()) -> Principal:
    return Principal(
        user_id=1,
        login_id="tester",
        user_nm="테스터",
        roles=frozenset(roles),
        granted=frozenset(granted),
    )


def test_permission_set_has_exactly_fourteen() -> None:
    """설계 §17.2 가 확정한 전체 권한 집합은 14종이다."""
    assert len(permissions.ALL_PERMISSIONS) == 14


def test_role_set_has_exactly_six() -> None:
    assert len(permissions.ALL_ROLES) == 6


def test_granted_permission_passes() -> None:
    p = principal(permissions.TARGET_READ)
    assert p.has(permissions.TARGET_READ)
    p.require(permissions.TARGET_READ)


def test_missing_permission_is_denied() -> None:
    p = principal(permissions.TARGET_READ)
    assert not p.has(permissions.USER_MANAGE)
    with pytest.raises(PermissionDeniedError) as exc:
        p.require(permissions.USER_MANAGE)
    assert exc.value.required == permissions.USER_MANAGE


def test_unknown_permission_string_is_always_denied() -> None:
    """계약 밖 문자열은 부여돼 있어도 거부한다(default-deny).

    임의 문자열을 권한으로 받으면 오타 하나가 인가 우회가 된다.
    """
    p = principal("target:read:all", "admin:*", "")
    assert not p.has("target:read:all")
    assert not p.has("admin:*")
    with pytest.raises(PermissionDeniedError):
        p.require("target:read:all")


def test_empty_principal_denies_everything() -> None:
    p = principal()
    for permission in permissions.ALL_PERMISSIONS:
        assert not p.has(permission)


def test_primary_role_is_deterministic() -> None:
    a = principal(roles=("ADMIN", "AUDITOR"))
    b = principal(roles=("AUDITOR", "ADMIN"))
    assert a.primary_role == b.primary_role == "ADMIN"


def test_primary_role_is_none_without_roles() -> None:
    assert principal().primary_role is None


def test_high_risk_permissions_require_reauth() -> None:
    """설계 §18 최고 등급은 재인증을 요구한다."""
    assert permissions.COMMAND_RERUN in permissions.PERMISSIONS_REQUIRING_REAUTH
    assert permissions.COMMAND_RESYNC in permissions.PERMISSIONS_REQUIRING_REAUTH
    assert permissions.USER_MANAGE in permissions.PERMISSIONS_REQUIRING_REAUTH


def test_read_permissions_do_not_require_reauth() -> None:
    for permission in (
        permissions.TARGET_READ,
        permissions.BATCH_READ,
        permissions.POLICY_READ,
        permissions.AUDIT_READ,
    ):
        assert permission not in permissions.PERMISSIONS_REQUIRING_REAUTH


def test_reauth_set_is_a_subset_of_all_permissions() -> None:
    assert permissions.PERMISSIONS_REQUIRING_REAUTH <= permissions.ALL_PERMISSIONS


def test_risk_levels_match_the_ddl_check() -> None:
    """TW_APPROVAL.risk_level_cd CHECK 와 같은 집합이어야 한다."""
    assert {"LOW", "MEDIUM", "HIGH", "CRITICAL"} == permissions.ALL_RISK_LEVELS
