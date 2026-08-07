"""감사 마스킹 단위 테스트.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §19.1

비밀번호·토큰·DSN 은 마스킹한다. DB 를 쓰지 않는다.
"""

from __future__ import annotations

import json

import pytest

from lifelaw_web.audit.writer import MASK, mask


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "Password",
        "user_password",
        "passwd",
        "secret",
        "session_secret",
        "token",
        "csrf_token",
        "credential",
        "dsn",
        "conninfo",
        "authorization",
        "cookie",
        "password_hash",
    ],
)
def test_sensitive_keys_are_masked(key: str) -> None:
    assert mask({key: "leaked"}) == {key: MASK}


def test_nested_structures_are_masked() -> None:
    payload = {
        "user": {"login_id": "admin", "password": "leaked"},
        "sessions": [{"token": "leaked"}, {"token": "leaked"}],
    }
    masked = mask(payload)
    assert masked["user"]["login_id"] == "admin"
    assert masked["user"]["password"] == MASK
    assert all(item["token"] == MASK for item in masked["sessions"])


def test_non_sensitive_values_survive() -> None:
    payload = {"login_id": "admin", "roles": ["ADMIN"], "count": 3, "ok": True}
    assert mask(payload) == payload


def test_masking_is_key_based_not_value_based() -> None:
    """값에 'password' 가 들어 있어도 키가 안전하면 남긴다.

    사유(reason) 같은 자유 문구를 통째로 가려버리면 감사 가치가 사라진다.
    """
    payload = {"reason": "사용자가 password 정책 변경을 요청함"}
    assert mask(payload) == payload


def test_masked_payload_is_json_serialisable() -> None:
    payload = {"password": "leaked", "nested": {"token": "leaked"}}
    rendered = json.dumps(mask(payload), ensure_ascii=False)
    assert "leaked" not in rendered
    assert MASK in rendered
