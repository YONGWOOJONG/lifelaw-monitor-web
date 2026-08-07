"""비밀번호 해싱과 검증.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7 §17.4
      scripts/db/migrations/0001_create_tw_schema.sql (ck_tw_user_pwd_argon2)

Argon2id 를 쓴다. bcrypt 의 72바이트 절단 문제가 없고, DDL 제약이
`$argon2id$` 접두사를 강제한다.
"""

from __future__ import annotations

from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.profiles import RFC_9106_LOW_MEMORY

ARGON2_PREFIX: Final = "$argon2id$"

# RFC 9106 low-memory 프로파일 (m=64MiB, t=3, p=4).
_hasher: Final = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)


class PasswordError(RuntimeError):
    """비밀번호 처리 오류. 값을 노출하지 않는다."""


def hash_password(plaintext: str) -> str:
    """비밀번호를 Argon2id 로 해싱하고, 저장 전에 자기 검증한다."""
    if not plaintext:
        raise PasswordError("빈 비밀번호는 허용하지 않습니다.")
    encoded = _hasher.hash(plaintext)
    if not encoded.startswith(ARGON2_PREFIX):
        raise PasswordError("해시 형식이 Argon2id 가 아닙니다.")
    # 저장할 해시로 원문이 실제 검증되는지 확인한다.
    _hasher.verify(encoded, plaintext)
    return encoded


def verify_password(encoded: str, plaintext: str) -> bool:
    """검증 결과를 bool 로 돌려준다.

    실패 사유(불일치 / 해시 손상)를 호출자에게 구분해 주지 않는다. 인증 응답이
    사유에 따라 달라지면 계정 존재 여부가 새어나간다.
    """
    if not encoded or not plaintext:
        return False
    try:
        return _hasher.verify(encoded, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(encoded: str) -> bool:
    """저장된 해시의 파라미터가 현재 정책보다 약하면 True."""
    try:
        return _hasher.check_needs_rehash(encoded)
    except InvalidHashError:
        return True
