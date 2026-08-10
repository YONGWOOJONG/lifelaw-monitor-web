"""서버 측 세션 (설계 §17.4, A-04 승인).

규칙:
  - 세션 토큰은 CSPRNG 로 만들고 **원본을 저장하지 않는다.** SHA-256 만 남긴다.
    DB 가 유출돼도 세션을 탈취할 수 없다.
  - 쿠키에는 식별자만 담는다. 역할·권한을 담지 않는다.
  - 권한은 매 요청 서버에서 재조회한다. 로그인 시점 스냅샷을 신뢰하지 않는다.
  - 로그아웃과 권한 변경은 서버 측 세션을 **삭제**해 즉시 무효화한다.

DB 권한: TW_SESSION 은 SELECT/INSERT/DELETE 와 UPDATE(last_seen_at, reauth_at)
만 부여돼 있다. 세션 소유자나 만료 시각을 사후에 바꾸는 경로는 열려 있지 않다.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

TOKEN_BYTES: Final = 32


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def csrf_for(session_token_hash: str, session_secret: str) -> str:
    """세션의 CSRF 토큰. **저장하지 않고 세션에서 다시 계산한다.**

    난수를 발급해 해시만 저장하던 방식은 새로고침을 넘길 수 없었다. 쿠키는
    남아 세션이 살아 있는데 원본 토큰은 브라우저 메모리에만 있었고, 서버는
    해시만 갖고 있어 되돌려줄 수가 없었다. 그 결과 새로고침 뒤에는 비밀번호가
    맞아도 모든 상태 변경 요청이 `CSRF_FAILED` 로 막혔다 — 재인증 자체가
    POST 라 재인증으로 회복할 수도 없었다.

    재발급으로 풀 수는 없다. `TW_SESSION` 의 UPDATE 권한이 `last_seen_at` 과
    `reauth_at` 두 컬럼뿐이라 런타임 롤은 `csrf_token_hash` 를 갱신하지 못한다
    (설계 §7.2 의 컬럼 단위 GRANT). 그래서 저장 대신 **유도**한다.

    비밀은 `LIFELAW_WEB_SESSION_SECRET` 이다. 세션 토큰 해시만 알아도 비밀
    없이는 계산할 수 없고, 비밀을 아는 공격자는 이미 세션을 위조할 수 있으므로
    이 유도가 새로 열어주는 것은 없다. 세션 수명 동안 값이 고정되므로 탭을
    여러 개 열어도 서로의 토큰을 무효화하지 않는다.
    """
    return hmac.new(
        session_secret.encode("utf-8"),
        session_token_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class IssuedSession:
    """발급 직후에만 존재하는 원본 토큰. 저장하지 않는다."""

    session_token: str
    csrf_token: str
    absolute_expires_at: datetime


@dataclass(frozen=True)
class SessionContext:
    """유효한 세션의 상태. 요청 처리 중 참조한다."""

    session_token_hash: str
    user_id: int
    login_id: str
    user_nm: str
    csrf_token_hash: str
    created_at: datetime
    last_seen_at: datetime
    absolute_expires_at: datetime
    reauth_at: datetime | None

    def reauth_is_fresh(self, now: datetime, valid_minutes: int) -> bool:
        if self.reauth_at is None:
            return False
        return self.reauth_at >= now - timedelta(minutes=valid_minutes)


def create_session(
    conn: Any,
    *,
    user_id: int,
    absolute_hours: int,
    source_ip: str | None,
    user_agent: str | None,
    now: datetime,
    session_secret: str,
) -> IssuedSession:
    session_token = new_token()
    session_token_hash = _hash_token(session_token)
    # 난수 대신 세션에서 유도한다. `csrf_for` 주석 참조 — 새로고침 뒤에 다시
    # 계산할 수 있어야 한다. 저장 형태는 그대로 해시다.
    csrf_token = csrf_for(session_token_hash, session_secret)
    expires_at = now + timedelta(hours=absolute_hours)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tw_session (
                session_token_hash, user_id, csrf_token_hash,
                source_ip, user_agent, created_at, last_seen_at, absolute_expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_token_hash,
                user_id,
                _hash_token(csrf_token),
                source_ip,
                (user_agent or "")[:500] or None,
                now,
                now,
                expires_at,
            ),
        )
    return IssuedSession(
        session_token=session_token,
        csrf_token=csrf_token,
        absolute_expires_at=expires_at,
    )


def resolve_session(
    conn: Any, *, session_token: str, idle_minutes: int, now: datetime
) -> SessionContext | None:
    """토큰으로 세션을 찾고 만료를 판정한다.

    만료된 세션은 발견 즉시 삭제한다. 만료 여부를 조회 시점에만 판단하고
    행을 남겨두면 원장이 부풀고 오판 여지가 생긴다.
    """
    if not session_token:
        return None
    token_hash = _hash_token(session_token)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.session_token_hash, s.user_id, u.login_id, u.user_nm,
                   s.csrf_token_hash, s.created_at, s.last_seen_at,
                   s.absolute_expires_at, s.reauth_at, u.use_yn
              FROM tw_session s
              JOIN tw_user u ON u.user_id = s.user_id
             WHERE s.session_token_hash = %s
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        (
            stored_hash,
            user_id,
            login_id,
            user_nm,
            csrf_hash,
            created_at,
            last_seen_at,
            absolute_expires_at,
            reauth_at,
            use_yn,
        ) = row

        idle_deadline = now - timedelta(minutes=idle_minutes)
        expired = absolute_expires_at <= now or last_seen_at < idle_deadline
        # 비활성화된 계정의 세션은 즉시 무효다.
        if expired or use_yn != "Y":
            cur.execute("DELETE FROM tw_session WHERE session_token_hash = %s", (token_hash,))
            return None

        cur.execute(
            "UPDATE tw_session SET last_seen_at = %s WHERE session_token_hash = %s",
            (now, token_hash),
        )

    return SessionContext(
        session_token_hash=str(stored_hash),
        user_id=int(user_id),
        login_id=str(login_id),
        user_nm=str(user_nm),
        csrf_token_hash=str(csrf_hash),
        created_at=created_at,
        last_seen_at=now,
        absolute_expires_at=absolute_expires_at,
        reauth_at=reauth_at,
    )


def verify_csrf(session: SessionContext, csrf_token: str | None) -> bool:
    """CSRF 토큰을 상수 시간 비교한다."""
    if not csrf_token:
        return False
    return secrets.compare_digest(session.csrf_token_hash, _hash_token(csrf_token))


def mark_reauth(conn: Any, *, session_token_hash: str, now: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tw_session SET reauth_at = %s WHERE session_token_hash = %s",
            (now, session_token_hash),
        )


def revoke(conn: Any, *, session_token_hash: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tw_session WHERE session_token_hash = %s", (session_token_hash,))


def revoke_all_for_user(conn: Any, *, user_id: int) -> int:
    """권한 변경·비활성화 시 해당 사용자의 모든 세션을 무효화한다(설계 §17.4)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tw_session WHERE user_id = %s", (user_id,))
        return int(cur.rowcount)


def purge_expired(conn: Any, *, idle_minutes: int, now: datetime) -> int:
    """만료 세션을 정리한다. 운영 배치에서 주기적으로 호출할 수 있다."""
    idle_deadline = now - timedelta(minutes=idle_minutes)
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM tw_session
             WHERE absolute_expires_at <= %s OR last_seen_at < %s
            """,
            (now, idle_deadline),
        )
        return int(cur.rowcount)
