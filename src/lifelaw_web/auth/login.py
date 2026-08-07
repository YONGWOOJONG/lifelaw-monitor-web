"""로그인·재인증 처리.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.4 §18 §19

규칙:
  - 실패 사유를 응답으로 구분해 주지 않는다. 계정 없음과 비밀번호 불일치가
    다른 응답을 내면 계정 존재 여부가 새어나간다.
  - 계정이 없어도 비밀번호 검증을 수행해 응답 시간 차이를 줄인다.
  - 실패한 시도도 감사에 남긴다(설계 §19.1).
  - 잠금은 무차별 대입 방어다. 잠긴 동안에는 올바른 비밀번호도 거부한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from lifelaw_web.auth import passwords

# 계정이 없을 때도 검증 비용을 치르기 위한 더미 해시. 어떤 비밀번호와도
# 일치하지 않는다.
_DUMMY_HASH: Final = passwords.hash_password("lifelaw-web-nonexistent-account-probe")


class LoginOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class LoginResult:
    outcome: LoginOutcome
    user_id: int | None = None
    login_id: str | None = None
    user_nm: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is LoginOutcome.SUCCESS


@dataclass(frozen=True)
class _UserRow:
    user_id: int
    login_id: str
    user_nm: str
    password_hash: str
    use_yn: str
    failed_login_cnt: int
    locked_until: datetime | None


def _load_user(conn: Any, login_id: str) -> _UserRow | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, login_id, user_nm, password_hash, use_yn,
                   failed_login_cnt, locked_until
              FROM tw_user WHERE login_id = %s
            """,
            (login_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _UserRow(
        user_id=int(row[0]),
        login_id=str(row[1]),
        user_nm=str(row[2]),
        password_hash=str(row[3]),
        use_yn=str(row[4]),
        failed_login_cnt=int(row[5]),
        locked_until=row[6],
    )


def _register_failure(
    conn: Any, user: _UserRow, *, max_failed: int, lockout_minutes: int, now: datetime
) -> None:
    attempts = user.failed_login_cnt + 1
    locked_until = now + timedelta(minutes=lockout_minutes) if attempts >= max_failed else None
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tw_user
               SET failed_login_cnt = %s,
                   locked_until = COALESCE(%s, locked_until),
                   moder = 'system', mod_dt = %s
             WHERE user_id = %s
            """,
            (attempts, locked_until, now, user.user_id),
        )


def _register_success(conn: Any, user: _UserRow, *, now: datetime, rehashed: str | None) -> None:
    with conn.cursor() as cur:
        if rehashed is None:
            cur.execute(
                """
                UPDATE tw_user
                   SET failed_login_cnt = 0, locked_until = NULL,
                       last_login_at = %s, moder = 'system', mod_dt = %s
                 WHERE user_id = %s
                """,
                (now, now, user.user_id),
            )
        else:
            cur.execute(
                """
                UPDATE tw_user
                   SET failed_login_cnt = 0, locked_until = NULL,
                       last_login_at = %s, password_hash = %s,
                       pwd_changed_at = %s, moder = 'system', mod_dt = %s
                 WHERE user_id = %s
                """,
                (now, rehashed, now, now, user.user_id),
            )


def authenticate(
    conn: Any,
    *,
    login_id: str,
    password: str,
    max_failed: int,
    lockout_minutes: int,
    now: datetime,
) -> LoginResult:
    """자격증명을 검증한다. 세션은 만들지 않는다."""
    user = _load_user(conn, login_id)

    if user is None:
        # 계정이 없어도 같은 비용을 치른다. 응답 시간으로 계정 존재를 알 수 없게 한다.
        passwords.verify_password(_DUMMY_HASH, password)
        return LoginResult(LoginOutcome.INVALID_CREDENTIALS)

    if user.use_yn != "Y":
        passwords.verify_password(_DUMMY_HASH, password)
        return LoginResult(LoginOutcome.DISABLED, user_id=user.user_id, login_id=user.login_id)

    if user.locked_until is not None and user.locked_until > now:
        passwords.verify_password(_DUMMY_HASH, password)
        return LoginResult(LoginOutcome.LOCKED, user_id=user.user_id, login_id=user.login_id)

    if not passwords.verify_password(user.password_hash, password):
        _register_failure(
            conn, user, max_failed=max_failed, lockout_minutes=lockout_minutes, now=now
        )
        return LoginResult(
            LoginOutcome.INVALID_CREDENTIALS, user_id=user.user_id, login_id=user.login_id
        )

    needs_rehash = passwords.needs_rehash(user.password_hash)
    rehashed = passwords.hash_password(password) if needs_rehash else None
    _register_success(conn, user, now=now, rehashed=rehashed)
    return LoginResult(
        LoginOutcome.SUCCESS,
        user_id=user.user_id,
        login_id=user.login_id,
        user_nm=user.user_nm,
    )


def verify_current_password(conn: Any, *, user_id: int, password: str) -> bool:
    """재인증용. 이미 로그인한 사용자의 비밀번호를 다시 확인한다(설계 §18).

    세션 재사용으로 대체하지 않는다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT password_hash FROM tw_user WHERE user_id = %s AND use_yn = 'Y'",
            (user_id,),
        )
        row = cur.fetchone()
    if row is None:
        return False
    return passwords.verify_password(str(row[0]), password)
