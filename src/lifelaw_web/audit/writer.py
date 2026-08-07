"""감사 기록 — append-only.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §15 §19.1
      scripts/db/grants/0001_grants.sql (TW_AUDIT_LOG 은 SELECT/INSERT 만)

규칙:
  - **UPDATE/DELETE 경로를 만들지 않는다.** DB 권한에서도 부여되어 있지 않다.
    애플리케이션 규율만으로는 부족하다는 것이 설계의 판단이다.
  - 변경 전후 값을 함께 남긴다. 누가, 언제, 무엇을, 왜.
  - **실패한 시도도 남긴다.** 권한 거부와 배리어 타임아웃도 감사 대상이다.
  - 비밀번호·토큰·DSN 은 마스킹한다.
"""

from __future__ import annotations

import json
from typing import Any, Final

from lifelaw_web.rbac.guard import Principal

MASK: Final = "***"

# 키 이름에 이 조각이 들어가면 값을 마스킹한다. 설정 검사(§6)와 달리 여기서는
# 부분 일치를 쓴다 — 감사 페이로드는 임의 구조라서 키 이름이 다양하다.
SENSITIVE_KEY_PARTS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "dsn",
    "conninfo",
    "authorization",
    "cookie",
    "hash",
)

RESULT_SUCCESS: Final = "SUCCESS"
RESULT_DENIED: Final = "DENIED"
RESULT_FAILED: Final = "FAILED"
RESULT_TIMEOUT: Final = "TIMEOUT"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def mask(value: Any) -> Any:
    """중첩 구조를 훑어 민감한 키의 값을 가린다."""
    if isinstance(value, dict):
        return {k: (MASK if _is_sensitive(str(k)) else mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(item) for item in value]
    return value


def _as_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(mask(value), ensure_ascii=False, default=str)


def record(
    conn: Any,
    *,
    actor: str,
    action: str,
    result_cd: str,
    actor_role_cd: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    before_value: Any = None,
    after_value: Any = None,
    reason: str | None = None,
    approval_id: int | None = None,
    idempotency_key: str | None = None,
) -> int:
    """감사 행 하나를 남기고 audit_id 를 돌려준다."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tw_audit_log (
                actor, actor_role_cd, source_ip, user_agent,
                action, target_type, target_id,
                before_value, after_value, reason,
                approval_id, idempotency_key, result_cd
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING audit_id
            """,
            (
                actor,
                actor_role_cd,
                source_ip,
                (user_agent or "")[:500] or None,
                action,
                target_type,
                target_id,
                _as_json(before_value),
                _as_json(after_value),
                reason,
                approval_id,
                idempotency_key,
                result_cd,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("감사 기록 INSERT 가 audit_id 를 반환하지 않았습니다.")
    return int(row[0])


def record_for(
    conn: Any,
    principal: Principal | None,
    *,
    actor_fallback: str,
    action: str,
    result_cd: str,
    **kwargs: Any,
) -> int:
    """주체가 있으면 그 정보로, 없으면 fallback 으로 기록한다.

    로그인 실패처럼 아직 주체가 확정되지 않은 사건도 반드시 남긴다.
    """
    if principal is None:
        return record(conn, actor=actor_fallback, action=action, result_cd=result_cd, **kwargs)
    return record(
        conn,
        actor=principal.login_id,
        actor_role_cd=principal.primary_role,
        action=action,
        result_cd=result_cd,
        **kwargs,
    )
