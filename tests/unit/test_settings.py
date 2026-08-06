"""설정·secret fail-closed 단위 테스트.

권위: DESIGN_project_structure_and_toolchain_v0_1.md §6

DB 를 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lifelaw_web.settings import (
    ENV_DB_PASSWORD,
    ENV_DB_USER,
    ENV_SESSION_SECRET,
    SettingsError,
    find_forbidden_config_keys,
    load_config,
    load_secrets,
)

VALID_CONFIG = {
    "postgres": {"host": "127.0.0.1", "port": 5432, "database": "lifelaw_c"},
    "artifact_root": "C:/artifacts",
    "session": {"idle_minutes": 30, "absolute_hours": 12},
}

VALID_ENV = {
    ENV_DB_USER: "lifelaw_web_app",
    ENV_DB_PASSWORD: "pw",
    ENV_SESSION_SECRET: "secret-value",
}


def write_config(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "web.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_config_loads(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, VALID_CONFIG))
    assert config.postgres.database == "lifelaw_c"
    assert config.session.idle_minutes == 30


def test_missing_config_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="설정 파일이 없습니다"):
        load_config(tmp_path / "absent.json")


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_CONFIG, "postgres": {**VALID_CONFIG["postgres"], "password": "leak"}},
        {**VALID_CONFIG, "postgres": {**VALID_CONFIG["postgres"], "user": "leak"}},
        {**VALID_CONFIG, "secret": "leak"},
    ],
    ids=["nested-password", "nested-user", "top-level-secret"],
)
def test_credential_keys_in_config_are_rejected(tmp_path: Path, payload: dict[str, object]) -> None:
    with pytest.raises(SettingsError, match="자격증명 키"):
        load_config(write_config(tmp_path, payload))


def test_forbidden_key_detection_is_key_based_not_text_based() -> None:
    """설명 문자열에 'password' 가 들어가도 오탐하지 않는다.

    config/web.example.json 에 주석용 필드를 두지 않은 이유가 이것이다.
    """
    payload = {"note": "do not put a password here", "postgres": VALID_CONFIG["postgres"]}
    assert find_forbidden_config_keys(payload) == []


def test_forbidden_key_detection_reports_full_path() -> None:
    payload = {"postgres": {"password": "x"}, "session": {"secret": "y"}}
    assert find_forbidden_config_keys(payload) == ["postgres.password", "session.secret"]


def test_unknown_config_key_is_rejected(tmp_path: Path) -> None:
    payload = {**VALID_CONFIG, "unexpected": 1}
    with pytest.raises(SettingsError, match="항목 오류"):
        load_config(write_config(tmp_path, payload))


def test_invalid_port_is_rejected(tmp_path: Path) -> None:
    payload = {**VALID_CONFIG, "postgres": {**VALID_CONFIG["postgres"], "port": 0}}
    with pytest.raises(SettingsError, match="항목 오류"):
        load_config(write_config(tmp_path, payload))


def test_non_object_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="최상위가 객체가 아닙니다"):
        load_config(write_config(tmp_path, [1, 2, 3]))


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "web.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SettingsError, match="JSON 구문 오류"):
        load_config(path)


def test_secrets_load_from_env() -> None:
    secrets = load_secrets(dict(VALID_ENV))
    assert secrets.db_user == "lifelaw_web_app"


@pytest.mark.parametrize("missing", sorted(VALID_ENV))
def test_missing_env_var_is_rejected(missing: str) -> None:
    env = {k: v for k, v in VALID_ENV.items() if k != missing}
    with pytest.raises(SettingsError, match=missing):
        load_secrets(env)


def test_empty_env_var_is_treated_as_missing() -> None:
    env = {**VALID_ENV, ENV_DB_PASSWORD: ""}
    with pytest.raises(SettingsError, match=ENV_DB_PASSWORD):
        load_secrets(env)


def test_secrets_repr_does_not_leak_values() -> None:
    secrets = load_secrets(dict(VALID_ENV))
    rendered = repr(secrets)
    assert "secret-value" not in rendered
    assert "pw" not in rendered
