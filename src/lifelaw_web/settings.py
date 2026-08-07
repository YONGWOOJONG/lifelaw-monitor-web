"""설정과 secret 로딩 — fail-closed.

권위: DESIGN_project_structure_and_toolchain_v0_1.md §6
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7 §17.4

규칙:
  1. 환경변수가 하나라도 없으면 기동을 실패시킨다. 기본값으로 대체하지 않는다.
  2. 설정 JSON 에 user/password/secret 키가 있으면 거부한다.
     판정은 **키 이름 기준**이다. 파일 전체를 문자열로 훑으면 설명 문구에
     "password" 가 들어간 정상 설정도 거부되는 오탐이 난다.
  3. 오류 메시지에 값을 담지 않는다. 키 이름만 담는다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger("lifelaw_web.settings")

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH: Final = PROJECT_ROOT / "config" / "web.json"

FORBIDDEN_CONFIG_KEYS: Final[frozenset[str]] = frozenset({"user", "password", "secret"})

# 아래 세 개는 환경변수 **이름**이며 값이 아니다. ruff S105 는 이름만 보고
# 하드코딩된 비밀로 오탐하므로 사유를 남기고 무시한다.
ENV_DB_USER: Final = "LIFELAW_WEB_DB_USER"
ENV_DB_PASSWORD: Final = "LIFELAW_WEB_DB_PASSWORD"  # noqa: S105
ENV_SESSION_SECRET: Final = "LIFELAW_WEB_SESSION_SECRET"  # noqa: S105

# D-26: batch_ymd 는 서울 업무일자다. 세션 타임존을 서버 기본값에 맡기지 않는다.
SESSION_TIME_ZONE: Final = "Asia/Seoul"


class SettingsError(RuntimeError):
    """설정 오류. 값을 노출하지 않는다."""


class PostgresConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1)


class SessionConfig(BaseModel):
    """세션과 쿠키 설정 (설계 §17.4).

    `cookie_secure` 는 **기본이 true** 다. 로컬 개발은 http://localhost 라
    Secure 쿠키가 전송되지 않으므로 내릴 수 있게 두되, 내린 상태로 기동하면
    경고를 남긴다(§17.4 A안, 사용자 승인 2026-08-06). 운영에서 실수로 꺼지면
    로그에 흔적이 남는다.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    idle_minutes: int = Field(ge=1, le=24 * 60)
    absolute_hours: int = Field(ge=1, le=24 * 30)
    reauth_valid_minutes: int = Field(default=5, ge=1, le=60)
    cookie_name: str = Field(default="lifelaw_session", min_length=1, max_length=64)
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict"] = "lax"
    max_failed_logins: int = Field(default=5, ge=1, le=100)
    lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)


class WebConfig(BaseModel):
    """config/web.json 의 구조. 비밀이 아닌 값만 담는다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    postgres: PostgresConfig
    artifact_root: str = Field(min_length=1)
    session: SessionConfig
    # 상태 변경 요청의 Origin 허용 목록. 동일 출처 배포가 전제이므로 보통
    # 자기 오리진 하나만 둔다(설계 §17.4 강제 조항 1·2). 빈 목록이면 Origin
    # 헤더가 있는 요청을 전부 거부한다 — 열어두는 것보다 닫아두는 쪽이 맞다.
    allowed_origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class Secrets:
    """환경변수로 주입되는 자격증명. 로그와 예외 메시지에 담지 않는다."""

    db_user: str
    db_password: str
    session_secret: str

    def __repr__(self) -> str:  # pragma: no cover - 방어용
        return "Secrets(db_user=***, db_password=***, session_secret=***)"


@dataclass(frozen=True)
class Settings:
    config: WebConfig
    secrets: Secrets
    config_path: Path

    @property
    def conninfo_kwargs(self) -> dict[str, Any]:
        pg = self.config.postgres
        return {
            "host": pg.host,
            "port": pg.port,
            "dbname": pg.database,
            "user": self.secrets.db_user,
            "password": self.secrets.db_password,
        }


def _walk_keys(obj: Any, prefix: str = "") -> list[str]:
    """중첩 dict 의 모든 키 경로를 모은다. 값은 보지 않는다."""
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.append(prefix + key)
            found.extend(_walk_keys(value, f"{prefix}{key}."))
    return found


def find_forbidden_config_keys(raw: Any) -> list[str]:
    """설정에 들어 있으면 안 되는 자격증명 키 경로를 돌려준다."""
    return sorted(
        path
        for path in _walk_keys(raw)
        if path.rsplit(".", maxsplit=1)[-1].lower() in FORBIDDEN_CONFIG_KEYS
    )


def load_config(path: Path | None = None) -> WebConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise SettingsError(f"설정 파일이 없습니다: {config_path.name}")

    try:
        raw: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SettingsError(
            f"설정 파일 JSON 구문 오류: {config_path.name} line {exc.lineno}"
        ) from exc

    if not isinstance(raw, dict):
        raise SettingsError(f"설정 파일 최상위가 객체가 아닙니다: {config_path.name}")

    leaked = find_forbidden_config_keys(raw)
    if leaked:
        raise SettingsError(
            "설정 파일에 자격증명 키가 있습니다. 환경변수로 옮기세요: " + ", ".join(leaked)
        )

    try:
        return WebConfig.model_validate(raw)
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in exc.errors())
        raise SettingsError(f"설정 파일 항목 오류: {fields}") from exc


def load_secrets(env: dict[str, str] | None = None) -> Secrets:
    source = os.environ if env is None else env
    missing = [
        name
        for name in (ENV_DB_USER, ENV_DB_PASSWORD, ENV_SESSION_SECRET)
        if not source.get(name)
    ]
    if missing:
        raise SettingsError(
            "필수 환경변수가 없습니다. 기본값으로 대체하지 않습니다: " + ", ".join(missing)
        )
    return Secrets(
        db_user=source[ENV_DB_USER],
        db_password=source[ENV_DB_PASSWORD],
        session_secret=source[ENV_SESSION_SECRET],
    )


def warn_on_weakened_security(config: WebConfig) -> list[str]:
    """보안을 약화시킨 설정에 대해 경고 문구를 만든다.

    거부하지 않는다 — 로컬 개발에는 필요한 완화다. 다만 **조용히 넘어가지
    않는다.** 운영에서 실수로 켜져 있으면 로그에 남는다.
    """
    warnings: list[str] = []
    if not config.session.cookie_secure:
        warnings.append(
            "session.cookie_secure=false — 세션 쿠키가 평문 HTTP 로 전송될 수 있습니다. "
            "로컬 개발 전용 설정이며 운영에서는 반드시 true 여야 합니다."
        )
    if not config.allowed_origins:
        warnings.append(
            "allowed_origins 가 비어 있습니다 — Origin 헤더가 있는 상태 변경 요청은 "
            "전부 거부됩니다. 브라우저에서 쓰려면 자기 오리진을 등록하세요."
        )
    for message in warnings:
        logger.warning(message)
    return warnings


def load_settings(config_path: Path | None = None, env: dict[str, str] | None = None) -> Settings:
    """설정과 secret 을 함께 읽는다. 하나라도 실패하면 예외를 던진다."""
    resolved = config_path or DEFAULT_CONFIG_PATH
    config = load_config(resolved)
    warn_on_weakened_security(config)
    return Settings(
        config=config,
        secrets=load_secrets(env),
        config_path=resolved,
    )
