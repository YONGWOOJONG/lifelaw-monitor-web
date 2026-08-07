"""권한과 역할 상수 — 코드 상의 단일 출처.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17 (A-05 승인)
      DESIGN_admin_screen_inventory_v0_1.md §5 화면-권한 매트릭스
      scripts/db/migrations/0001_create_tw_schema.sql (seed)

규칙:
  - 아래 14개가 **확정된 전체 권한 집합**이다. 라우터에 문자열 리터럴을 직접
    쓰지 않고 이 상수를 쓴다.
  - 권한 추가는 설계 문서 개정 사항이다. 임의 문자열을 권한으로 받지 않는다.
  - **역할은 누적이 아니다**(사용자 결정 2026-08-06). 상위 역할이 하위 역할의
    쓰기 권한을 자동으로 갖지 않는다. 특히 ADMIN 은 command:approve 를 갖지
    않는다 — 가지면 계정 관리자가 자기 신청을 승인할 수 있어 §17.3 4-eyes 가
    무너진다.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# 권한 14종
# ---------------------------------------------------------------------------

TARGET_READ: Final = "target:read"
TARGET_HISTORY_READ: Final = "target:history:read"
BATCH_READ: Final = "batch:read"
POLICY_READ: Final = "policy:read"
POLICY_SITE_WRITE: Final = "policy:site:write"
POLICY_TARGET_WRITE: Final = "policy:target:write"
COMMAND_RERUN: Final = "command:rerun"
COMMAND_CANCEL: Final = "command:cancel"
COMMAND_RESET: Final = "command:reset"
COMMAND_RESYNC: Final = "command:resync"
COMMAND_APPROVE: Final = "command:approve"
ARTIFACT_READ: Final = "artifact:read"
AUDIT_READ: Final = "audit:read"
USER_MANAGE: Final = "user:manage"

ALL_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        TARGET_READ,
        TARGET_HISTORY_READ,
        BATCH_READ,
        POLICY_READ,
        POLICY_SITE_WRITE,
        POLICY_TARGET_WRITE,
        COMMAND_RERUN,
        COMMAND_CANCEL,
        COMMAND_RESET,
        COMMAND_RESYNC,
        COMMAND_APPROVE,
        ARTIFACT_READ,
        AUDIT_READ,
        USER_MANAGE,
    }
)

# ---------------------------------------------------------------------------
# 역할 6종
# ---------------------------------------------------------------------------

VIEWER: Final = "VIEWER"
OPERATOR: Final = "OPERATOR"
POLICY_MANAGER: Final = "POLICY_MANAGER"
APPROVER: Final = "APPROVER"
ADMIN: Final = "ADMIN"
AUDITOR: Final = "AUDITOR"

ALL_ROLES: Final[frozenset[str]] = frozenset(
    {VIEWER, OPERATOR, POLICY_MANAGER, APPROVER, ADMIN, AUDITOR}
)

# ---------------------------------------------------------------------------
# 위험 등급 (설계 §18)
# ---------------------------------------------------------------------------

RISK_LOW: Final = "LOW"
RISK_MEDIUM: Final = "MEDIUM"
RISK_HIGH: Final = "HIGH"
RISK_CRITICAL: Final = "CRITICAL"

ALL_RISK_LEVELS: Final[frozenset[str]] = frozenset(
    {RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL}
)

# 최고 위험 작업은 재인증을 요구한다(설계 §18).
PERMISSIONS_REQUIRING_REAUTH: Final[frozenset[str]] = frozenset(
    {COMMAND_RERUN, COMMAND_RESYNC, USER_MANAGE}
)
