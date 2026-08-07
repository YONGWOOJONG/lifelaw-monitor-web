"""권한 검사 — default-deny.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3 §17.4 §18

규칙:
  - 명시적으로 부여된 권한만 통과한다. 모르는 권한은 거부한다.
  - **권한은 매 요청 서버에서 재조회한다.** 로그인 시점 스냅샷을 신뢰하지
    않는다. 권한을 회수했는데 세션이 살아 있는 상태를 만들지 않는다.
  - 프론트엔드의 메뉴 숨김은 인가가 아니다. 검증은 전부 여기서 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lifelaw_web.rbac import permissions


class PermissionDeniedError(Exception):
    """인가 실패. 인증 실패(401)와 구분해 403 으로 매핑한다."""

    def __init__(self, required: str) -> None:
        self.required = required
        super().__init__(f"권한 없음: {required}")


class ReauthRequiredError(Exception):
    """재인증이 필요한 작업. 401 이 아니라 별도 응답으로 구분한다."""

    def __init__(self, required: str) -> None:
        self.required = required
        super().__init__(f"재인증 필요: {required}")


@dataclass(frozen=True)
class Principal:
    """요청 시점의 주체. 권한은 매 요청 재조회한 값이다."""

    user_id: int
    login_id: str
    user_nm: str
    roles: frozenset[str]
    granted: frozenset[str]

    def has(self, permission: str) -> bool:
        # 알려지지 않은 권한 문자열은 항상 거부한다(default-deny).
        if permission not in permissions.ALL_PERMISSIONS:
            return False
        return permission in self.granted

    def require(self, permission: str) -> None:
        if not self.has(permission):
            raise PermissionDeniedError(permission)

    @property
    def primary_role(self) -> str | None:
        """감사 기록용 대표 역할. 결정적으로 고른다."""
        return sorted(self.roles)[0] if self.roles else None


def load_principal(conn: Any, *, user_id: int, login_id: str, user_nm: str) -> Principal:
    """사용자의 역할과 유효 권한을 DB 에서 다시 읽는다."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ur.role_cd, rp.perm_cd
              FROM tw_user_role ur
              LEFT JOIN tw_role_permission rp ON rp.role_cd = ur.role_cd
             WHERE ur.user_id = %s
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    roles = {str(r[0]) for r in rows}
    granted = {str(r[1]) for r in rows if r[1] is not None}
    # DB 에 있더라도 계약 밖 권한 문자열은 받아들이지 않는다.
    granted &= permissions.ALL_PERMISSIONS
    return Principal(
        user_id=user_id,
        login_id=login_id,
        user_nm=user_nm,
        roles=frozenset(roles),
        granted=frozenset(granted),
    )


def require_reauth_for(permission: str) -> bool:
    return permission in permissions.PERMISSIONS_REQUIRING_REAUTH
