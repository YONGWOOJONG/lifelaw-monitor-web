"""사용자 관리 — 화면 S-18.

권위: DESIGN_admin_screen_inventory_v0_1.md S-18 (쓰기 C·R·U, 위험 최고)
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7.2 §17 §18

**삭제가 없다.** §7.2 가 `TW_USER` 를 C·R·U 로 규정하고 "삭제는 비활성화로
대체"라고 못박았다. 계정을 지우면 `TW_AUDIT_LOG.actor` 가 가리키는 사람이
사라져 감사 기록이 고아가 된다. `use_yn='N'` 으로 막는다.

잠금 사고 방어(이 파일의 존재 이유 절반):
  - 자기 자신의 `user:manage` 를 스스로 떼지 못한다.
  - 자기 자신을 비활성화하지 못한다.
  - `user:manage` 를 가진 **마지막 활성 사용자**는 비활성화도 역할 해제도 못 한다.
셋 다 서버에서 막는다. 화면에서 버튼을 숨기는 것은 인가가 아니다(§17.3).
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from lifelaw_web.auth import passwords
from lifelaw_web.rbac import permissions

MIN_PASSWORD_LEN = 8


class AccountError(Exception):
    """계정 변경 거부. 화면에 그대로 보여도 되는 문장이다."""


def _rows_to_users(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["roles"] = list(item["roles"])
        out.append(item)
    return out


def list_users(conn: Any) -> list[dict[str, Any]]:
    """사용자 목록. 비밀번호 해시는 **절대 내리지 않는다.**"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.user_id, u.login_id, u.user_nm, u.use_yn,
                   u.pwd_changed_at, u.last_login_at,
                   u.failed_login_cnt, u.locked_until,
                   COALESCE(r.roles, ARRAY[]::varchar[]) AS roles
              FROM tw_user u
              LEFT JOIN (SELECT user_id, array_agg(role_cd ORDER BY role_cd) AS roles
                           FROM tw_user_role GROUP BY user_id) r ON r.user_id = u.user_id
             ORDER BY u.user_id
            """
        )
        return _rows_to_users(cur.fetchall())


def get_user(conn: Any, user_id: int) -> dict[str, Any] | None:
    for row in list_users(conn):
        if row["user_id"] == user_id:
            return row
    return None


def _roles_granting(conn: Any, permission: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT role_cd FROM tw_role_permission WHERE perm_cd = %s", (permission,))
        return {str(r[0]) for r in cur.fetchall()}


def _managers(conn: Any, *, exclude_user_id: int | None = None) -> set[int]:
    """활성 상태로 `user:manage` 를 실제로 가진 사용자 집합.

    역할 이름(`ADMIN`)이 아니라 **권한 매핑**으로 센다. S-19 에서 다른 역할에
    `user:manage` 를 붙였을 수 있고, 그때도 잠금 판정이 맞아야 한다.
    """
    roles = _roles_granting(conn, permissions.USER_MANAGE)
    if not roles:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT u.user_id
              FROM tw_user u JOIN tw_user_role ur ON ur.user_id = u.user_id
             WHERE u.use_yn = 'Y' AND ur.role_cd = ANY(%s)
            """,
            (sorted(roles),),
        )
        found = {int(r[0]) for r in cur.fetchall()}
    if exclude_user_id is not None:
        found.discard(exclude_user_id)
    return found


def _validate_roles(conn: Any, role_cds: list[str]) -> None:
    if not role_cds:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT role_cd FROM tw_role WHERE role_cd = ANY(%s)", (sorted(set(role_cds)),))
        known = {str(r[0]) for r in cur.fetchall()}
    unknown = sorted(set(role_cds) - known)
    if unknown:
        raise AccountError(f"알 수 없는 역할입니다: {', '.join(unknown)}")


def _check_password(plaintext: str) -> None:
    if len(plaintext) < MIN_PASSWORD_LEN:
        raise AccountError(f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다.")


def create_user(
    conn: Any, *, login_id: str, user_nm: str, password: str, role_cds: list[str], actor: str
) -> dict[str, Any]:
    login_id = login_id.strip()
    if not login_id:
        raise AccountError("로그인 ID 는 비어 있을 수 없습니다.")
    if not user_nm.strip():
        raise AccountError("이름은 비어 있을 수 없습니다.")
    _check_password(password)
    _validate_roles(conn, role_cds)

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM tw_user WHERE login_id = %s", (login_id,))
        if cur.fetchone():
            raise AccountError(f"이미 있는 로그인 ID 입니다: {login_id}")

        cur.execute(
            """
            INSERT INTO tw_user (login_id, user_nm, password_hash, use_yn, reger, moder)
            VALUES (%s, %s, %s, 'Y', %s, %s) RETURNING user_id
            """,
            (login_id, user_nm.strip(), passwords.hash_password(password), actor, actor),
        )
        row = cur.fetchone()
        if row is None:  # pragma: no cover - 방어용
            raise AccountError("사용자를 만들었으나 user_id 를 받지 못했습니다.")
        user_id = int(row[0])

        for role_cd in sorted(set(role_cds)):
            cur.execute(
                "INSERT INTO tw_user_role (user_id, role_cd, reger) VALUES (%s, %s, %s)",
                (user_id, role_cd, actor),
            )

    created = get_user(conn, user_id)
    if created is None:  # pragma: no cover - 방어용
        raise AccountError("사용자를 만들었으나 다시 읽지 못했습니다.")
    return created


def update_user(
    conn: Any, *, user_id: int, user_nm: str, actor: str, current: dict[str, Any]
) -> dict[str, Any]:
    """이름만 바꾼다. 역할과 활성 여부는 각각 전용 경로로 다룬다."""
    if not user_nm.strip():
        raise AccountError("이름은 비어 있을 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tw_user SET user_nm = %s, moder = %s, mod_dt = now() WHERE user_id = %s",
            (user_nm.strip(), actor, user_id),
        )
    updated = get_user(conn, user_id)
    if updated is None:  # pragma: no cover - 방어용
        raise AccountError("사용자를 바꿨으나 다시 읽지 못했습니다.")
    del current
    return updated


def set_roles(
    conn: Any, *, user_id: int, role_cds: list[str], actor: str, acting_user_id: int
) -> dict[str, Any]:
    """역할 집합을 통째로 교체한다. 최고 위험 경로다(§18 계정 권한 변경)."""
    current = get_user(conn, user_id)
    if current is None:
        raise AccountError("없는 사용자입니다.")
    _validate_roles(conn, role_cds)

    wanted = set(role_cds)
    held = set(current["roles"])
    if wanted == held:
        return current

    manage_roles = _roles_granting(conn, permissions.USER_MANAGE)
    loses_manage = bool(held & manage_roles) and not (wanted & manage_roles)

    if loses_manage:
        # 자기 자신에게서 관리 권한을 떼면 되돌릴 사람이 자기 자신뿐일 때 잠긴다.
        if user_id == acting_user_id:
            raise AccountError(
                "자기 자신에게서 user:manage 를 뗄 수 없습니다. "
                "다른 관리자에게 요청하세요."
            )
        if current["use_yn"] == "Y" and not _managers(conn, exclude_user_id=user_id):
            raise AccountError(
                "user:manage 를 가진 마지막 활성 사용자입니다. "
                "먼저 다른 사용자에게 관리 역할을 부여하세요."
            )

    with conn.cursor() as cur:
        for role_cd in sorted(held - wanted):
            cur.execute(
                "DELETE FROM tw_user_role WHERE user_id = %s AND role_cd = %s", (user_id, role_cd)
            )
        for role_cd in sorted(wanted - held):
            cur.execute(
                "INSERT INTO tw_user_role (user_id, role_cd, reger) VALUES (%s, %s, %s)",
                (user_id, role_cd, actor),
            )
        cur.execute(
            "UPDATE tw_user SET moder = %s, mod_dt = now() WHERE user_id = %s", (actor, user_id)
        )

    updated = get_user(conn, user_id)
    if updated is None:  # pragma: no cover - 방어용
        raise AccountError("역할을 바꿨으나 다시 읽지 못했습니다.")
    return updated


def set_active(
    conn: Any, *, user_id: int, active: bool, actor: str, acting_user_id: int
) -> dict[str, Any]:
    """계정 활성/비활성. 삭제 대신 쓰는 경로다(§7.2)."""
    current = get_user(conn, user_id)
    if current is None:
        raise AccountError("없는 사용자입니다.")

    if not active:
        if user_id == acting_user_id:
            raise AccountError("자기 자신을 비활성화할 수 없습니다.")
        if user_id in _managers(conn) and not _managers(conn, exclude_user_id=user_id):
            raise AccountError(
                "user:manage 를 가진 마지막 활성 사용자입니다. 비활성화하면 아무도 "
                "계정을 관리할 수 없습니다."
            )

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tw_user SET use_yn = %s, moder = %s, mod_dt = now() WHERE user_id = %s",
            ("Y" if active else "N", actor, user_id),
        )
        if not active:
            # 비활성화는 즉시 효력이 있어야 한다. 살아 있는 세션을 끊는다.
            cur.execute("DELETE FROM tw_session WHERE user_id = %s", (user_id,))

    updated = get_user(conn, user_id)
    if updated is None:  # pragma: no cover - 방어용
        raise AccountError("계정 상태를 바꿨으나 다시 읽지 못했습니다.")
    return updated


def reset_password(
    conn: Any, *, user_id: int, password: str, actor: str
) -> dict[str, Any]:
    """비밀번호 재설정. 잠금 카운터도 함께 푼다.

    부트스트랩 스크립트는 create-only 라 이 경로가 없으면 비밀번호를 잊은
    계정을 되살릴 방법이 아예 없다.
    """
    current = get_user(conn, user_id)
    if current is None:
        raise AccountError("없는 사용자입니다.")
    _check_password(password)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tw_user
               SET password_hash = %s, pwd_changed_at = now(),
                   failed_login_cnt = 0, locked_until = NULL,
                   moder = %s, mod_dt = now()
             WHERE user_id = %s
            """,
            (passwords.hash_password(password), actor, user_id),
        )
        # 비밀번호가 바뀌면 기존 세션은 신뢰할 수 없다.
        cur.execute("DELETE FROM tw_session WHERE user_id = %s", (user_id,))

    updated = get_user(conn, user_id)
    if updated is None:  # pragma: no cover - 방어용
        raise AccountError("비밀번호를 바꿨으나 다시 읽지 못했습니다.")
    return updated


def unlock(conn: Any, *, user_id: int, actor: str) -> dict[str, Any]:
    """로그인 실패 잠금 해제. 비밀번호는 건드리지 않는다."""
    current = get_user(conn, user_id)
    if current is None:
        raise AccountError("없는 사용자입니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tw_user SET failed_login_cnt = 0, locked_until = NULL,
                               moder = %s, mod_dt = now()
             WHERE user_id = %s
            """,
            (actor, user_id),
        )
    updated = get_user(conn, user_id)
    if updated is None:  # pragma: no cover - 방어용
        raise AccountError("잠금을 풀었으나 다시 읽지 못했습니다.")
    return updated
