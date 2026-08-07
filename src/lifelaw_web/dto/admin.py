"""관리 화면 요청·응답 DTO — S-18 사용자, S-19 역할·권한, S-20 감사 로그.

권위: DESIGN_admin_screen_inventory_v0_1.md S-18 S-19 S-20
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §18 §19

조회 DTO(`dto/read.py`)와 달리 여기에는 **요청** 모델이 있다. 쓰기 입력은
행 dict 를 그대로 받으면 안 된다 — 받는 순간 클라이언트가 아무 컬럼이나
보낼 수 있고, 그걸 막는 책임이 라우터로 흩어진다.

`reason` 이 거의 모든 요청에 필수인 이유는 §18 이다. 중위험 이상은 사유
없이 실행할 수 없고, 그 사유는 감사 로그에 남는다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REASON_MIN = 5
REASON_MAX = 1000


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


Reason = Field(min_length=REASON_MIN, max_length=REASON_MAX)


# 응답 **행**은 dict 로 내린다. `dto/read.py` 와 같은 이유다 — 행 스키마를 여기서
# 다시 선언하면 마이그레이션 SQL 과 이중 정의가 되어 C-1 류의 드리프트가 생긴다.
# 반대로 **요청**은 아래에서 엄격히 못박는다. 클라이언트가 아무 컬럼이나 보내지
# 못하게 막는 것이 쓰기 경로에서는 훨씬 중요하다.


class PermissionList(_Base):
    items: list[dict[str, Any]]


class RoleList(_Base):
    """행에는 `permissions`, `user_cnt`, `is_system` 이 함께 온다.

    `user_cnt` 는 삭제 전 영향 범위 표시용이고(§18 영향 미리보기),
    `is_system` 은 화면이 삭제 버튼을 잠그는 근거다.
    """

    items: list[dict[str, Any]]


class RoleCreateRequest(_Base):
    role_cd: str = Field(min_length=1, max_length=30)
    role_nm: str = Field(min_length=1, max_length=100)
    role_desc: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)
    reason: str = Reason


class RoleUpdateRequest(_Base):
    role_nm: str = Field(min_length=1, max_length=100)
    role_desc: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)
    reason: str = Reason
    # 사용자가 **보고 있던** 값. 그 사이 바뀌었으면 409 로 거부한다(§20).
    expected_role_nm: str
    expected_permissions: list[str]


class RoleDeleteRequest(_Base):
    reason: str = Reason


class UserList(_Base):
    """행에 `password_hash` 는 **없다.** `query/accounts.py` 가 애초에 뽑지 않는다."""

    items: list[dict[str, Any]]


class UserCreateRequest(_Base):
    login_id: str = Field(min_length=1, max_length=100)
    user_nm: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    roles: list[str] = Field(default_factory=list)
    reason: str = Reason


class UserUpdateRequest(_Base):
    user_nm: str = Field(min_length=1, max_length=100)
    reason: str = Reason


class UserRolesRequest(_Base):
    roles: list[str] = Field(default_factory=list)
    reason: str = Reason
    expected_roles: list[str]


class UserActiveRequest(_Base):
    active: bool
    reason: str = Reason


class PasswordResetRequest(_Base):
    password: str = Field(min_length=8, max_length=200)
    reason: str = Reason


class UnlockRequest(_Base):
    reason: str = Reason


class AuditPage(_Base):
    items: list[dict[str, Any]]
    limit: int
    offset: int
    has_more: bool


class AuditActionList(_Base):
    items: list[str]
