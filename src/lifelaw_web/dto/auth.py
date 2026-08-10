"""인증 관련 요청·응답 DTO.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §6 §17.4

규칙:
  - 모델 객체를 그대로 노출하지 않는다. 응답은 이 DTO 를 거친다.
  - 비밀번호와 해시는 **응답 모델에 존재하지 않는다.** 실수로 담을 수 없게 한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class ReauthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=1024)


class SessionInfo(BaseModel):
    """세션 상태. 만료 판단에 필요한 시각만 노출한다."""

    model_config = ConfigDict(extra="forbid")

    absolute_expires_at: str
    reauth_fresh: bool


class PrincipalResponse(BaseModel):
    """현재 사용자. 권한 목록은 **메뉴 표시 편의용**이며 인가가 아니다.

    설계 §17.3 — 프론트엔드의 메뉴 숨김은 인가가 아니다. 서버가 매 요청
    검증한다. 이 목록을 신뢰해 클라이언트가 접근을 결정하지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: int
    login_id: str
    user_nm: str
    roles: list[str]
    permissions: list[str]
    session: SessionInfo
    # 세션에서 유도한 CSRF 토큰. `/me` 가 이걸 함께 내리는 이유는 **새로고침**
    # 이다 — 쿠키는 남아 세션이 살아 있는데 원본 토큰은 브라우저 메모리에만
    # 있었고, 그래서 새로고침 뒤에는 재인증조차 CSRF_FAILED 로 막혔다.
    # 저장하지 않고 매번 계산하므로 세션 수명 동안 같은 값이다.
    csrf_token: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal: PrincipalResponse
    # CSRF 토큰은 본문으로 내려주고 클라이언트가 X-CSRF-Token 헤더로 되돌려준다.
    # 쿠키에 담지 않는다. `PrincipalResponse.csrf_token` 과 같은 값이며, 로그인
    # 응답의 기존 모양을 깨지 않으려고 이 자리도 유지한다.
    csrf_token: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    # 오류 응답에 내부 경로·DSN·스택트레이스를 담지 않는다(설계 §7).
    required_permission: str | None = None
