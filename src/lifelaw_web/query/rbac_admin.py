"""역할·권한 관리 — 화면 S-19.

권위: DESIGN_admin_screen_inventory_v0_1.md S-19 (쓰기 C·R·U·D, 위험 최고)
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7.2 §17 §18

┌──────────────────────────────────────────────────────────────────────────┐
│ 이 저장소에서 **삭제가 허용된 유일한 데이터**다.                          │
│                                                                          │
│ 수집기 소유 표는 SELECT 전용이거나 컬럼 한정 UPDATE 뿐이고, 감사·승인은  │
│ append-only 다(§15·§19). 역할과 역할-권한 매핑만 진짜 D 를 갖는다.       │
│ 그래서 이 파일의 삭제 경로에는 다른 곳보다 방어가 많다.                  │
└──────────────────────────────────────────────────────────────────────────┘

권한 목록(`TW_PERMISSION`)은 **여기서 만들지 않는다.** 권한은 코드가 검사하는
상수(`rbac/permissions.py`)와 1:1 이어야 하고, DB 에만 새 권한이 생기면 아무도
검사하지 않는 이름이 늘어난다. 관리 대상은 **역할과 매핑**이다.
"""

from __future__ import annotations

from typing import Any, Final

from psycopg.rows import dict_row

from lifelaw_web.rbac import permissions

# 시스템 역할. 이름을 코드가 알고 있으므로 삭제·개명을 막는다.
# (부트스트랩 ADMIN 이 사라지면 아무도 로그인해 복구할 수 없다.)
SYSTEM_ROLES: Final[frozenset[str]] = frozenset(
    {
        permissions.ADMIN,
        permissions.VIEWER,
        permissions.OPERATOR,
        permissions.POLICY_MANAGER,
        permissions.APPROVER,
        permissions.AUDITOR,
    }
)


class RbacError(Exception):
    """역할·권한 변경 거부. 메시지는 화면에 그대로 보여도 되는 문장이다."""


class VersionConflictError(Exception):
    """다른 사람이 먼저 바꿨다. 현재 값을 동봉해 409 로 매핑한다."""

    def __init__(self, message: str, current: Any) -> None:
        super().__init__(message)
        self.message = message
        self.current = current


def list_permissions(conn: Any) -> list[dict[str, Any]]:
    """권한 목록. 표시 전용이다."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT perm_cd, perm_nm, sort_ord FROM tw_permission ORDER BY sort_ord, perm_cd"
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row["sort_ord"] = int(row["sort_ord"])  # NUMERIC → Decimal 방지. list_roles 주석 참조.
    return rows


def list_roles(conn: Any) -> list[dict[str, Any]]:
    """역할 목록과 각 역할의 권한·사용자 수.

    사용자 수를 같이 내리는 이유: 삭제 버튼을 누르기 **전에** 영향 범위가
    보여야 한다(§18 영향 미리보기).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT r.role_cd,
                   r.role_nm,
                   r.role_desc,
                   r.sort_ord,
                   COALESCE(p.perms, ARRAY[]::varchar[]) AS permissions,
                   COALESCE(u.cnt, 0)                    AS user_cnt
              FROM tw_role r
              LEFT JOIN (SELECT role_cd, array_agg(perm_cd ORDER BY perm_cd) AS perms
                           FROM tw_role_permission GROUP BY role_cd) p ON p.role_cd = r.role_cd
              LEFT JOIN (SELECT role_cd, count(*) AS cnt
                           FROM tw_user_role GROUP BY role_cd) u ON u.role_cd = r.role_cd
             ORDER BY r.sort_ord, r.role_cd
            """
        )
        rows = [dict(r) for r in cur.fetchall()]

    for row in rows:
        row["permissions"] = list(row["permissions"])
        row["is_system"] = row["role_cd"] in SYSTEM_ROLES
        # sort_ord 는 NUMERIC 이라 psycopg 가 Decimal 로 준다. int 로 내리는 이유는
        # 이 행이 409 응답 본문(HTTPException detail)에 그대로 실리는데, 그 경로는
        # Pydantic 이 아니라 json.dumps 를 쓰기 때문이다 — Decimal 이면 500 이 된다.
        # (실측으로 잡았다. 200 응답만 보면 멀쩡해 보인다.)
        row["sort_ord"] = int(row["sort_ord"])
        row["user_cnt"] = int(row["user_cnt"])
    return rows


def get_role(conn: Any, role_cd: str) -> dict[str, Any] | None:
    for row in list_roles(conn):
        if row["role_cd"] == role_cd:
            return row
    return None


def _validate_permissions(perm_cds: list[str]) -> None:
    """알려지지 않은 권한을 거부한다.

    `Principal.has()` 가 default-deny 라 모르는 권한은 어차피 아무 문도 열지
    않는다. 그래도 여기서 막는 이유는, 붙는 순간 화면에는 "권한 있음"으로
    보이는데 실제로는 거부되는 **거짓 표시**가 생기기 때문이다.
    """
    unknown = sorted(set(perm_cds) - permissions.ALL_PERMISSIONS)
    if unknown:
        raise RbacError(f"알 수 없는 권한입니다: {', '.join(unknown)}")


def create_role(
    conn: Any, *, role_cd: str, role_nm: str, role_desc: str | None, perm_cds: list[str]
) -> dict[str, Any]:
    role_cd = role_cd.strip().upper()
    if not role_cd:
        raise RbacError("역할 코드는 비어 있을 수 없습니다.")
    if not role_nm.strip():
        raise RbacError("역할 이름은 비어 있을 수 없습니다.")
    _validate_permissions(perm_cds)

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM tw_role WHERE role_cd = %s", (role_cd,))
        if cur.fetchone():
            raise RbacError(f"이미 있는 역할 코드입니다: {role_cd}")

        cur.execute("SELECT COALESCE(max(sort_ord), 0) + 10 FROM tw_role")
        row = cur.fetchone()
        sort_ord = int(row[0]) if row else 10

        cur.execute(
            "INSERT INTO tw_role (role_cd, role_nm, role_desc, sort_ord) VALUES (%s, %s, %s, %s)",
            (role_cd, role_nm.strip(), (role_desc or "").strip() or None, sort_ord),
        )
        for perm_cd in sorted(set(perm_cds)):
            cur.execute(
                "INSERT INTO tw_role_permission (role_cd, perm_cd) VALUES (%s, %s)",
                (role_cd, perm_cd),
            )

    created = get_role(conn, role_cd)
    if created is None:  # pragma: no cover - 방어용
        raise RbacError("역할을 만들었으나 다시 읽지 못했습니다.")
    return created


def update_role(
    conn: Any,
    *,
    role_cd: str,
    role_nm: str,
    role_desc: str | None,
    perm_cds: list[str],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """역할 이름과 권한 집합을 바꾼다.

    `expected` 는 사용자가 **보고 있던 값**이다. 그 사이 다른 사람이 바꿨으면
    거부하고 현재 값을 돌려준다(§20 낙관적 잠금). 역할 표에는 버전 컬럼이
    없으므로 권한 집합과 이름 자체를 버전으로 쓴다.
    """
    current = get_role(conn, role_cd)
    if current is None:
        raise RbacError(f"없는 역할입니다: {role_cd}")

    if sorted(current["permissions"]) != sorted(expected.get("permissions", [])) or current[
        "role_nm"
    ] != expected.get("role_nm"):
        raise VersionConflictError(
            "다른 사용자가 이 역할을 먼저 변경했습니다. 현재 값을 확인하고 다시 결정하세요.",
            current,
        )

    if not role_nm.strip():
        raise RbacError("역할 이름은 비어 있을 수 없습니다.")
    _validate_permissions(perm_cds)

    # 시스템 역할은 이름·설명·권한을 바꿀 수 있지만 코드는 못 바꾼다(개명 금지).
    # 코드가 SYSTEM_ROLES 로 이 값을 알고 있기 때문이다.
    wanted = set(perm_cds)
    if role_cd == permissions.ADMIN and permissions.USER_MANAGE not in wanted:
        raise RbacError(
            "ADMIN 역할에서 user:manage 를 뺄 수 없습니다. "
            "빼는 순간 아무도 역할·권한을 되돌릴 수 없습니다."
        )

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tw_role SET role_nm = %s, role_desc = %s WHERE role_cd = %s",
            (role_nm.strip(), (role_desc or "").strip() or None, role_cd),
        )
        held = set(current["permissions"])
        for perm_cd in sorted(held - wanted):
            cur.execute(
                "DELETE FROM tw_role_permission WHERE role_cd = %s AND perm_cd = %s",
                (role_cd, perm_cd),
            )
        for perm_cd in sorted(wanted - held):
            cur.execute(
                "INSERT INTO tw_role_permission (role_cd, perm_cd) VALUES (%s, %s)",
                (role_cd, perm_cd),
            )

    updated = get_role(conn, role_cd)
    if updated is None:  # pragma: no cover - 방어용
        raise RbacError("역할을 바꿨으나 다시 읽지 못했습니다.")
    return updated


def delete_role(conn: Any, *, role_cd: str) -> dict[str, Any]:
    """역할을 지운다. 지워진 역할을 돌려준다(감사의 before 값으로 쓴다).

    막는 경우가 둘이다.
      - 시스템 역할 — 코드가 이름을 알고 있어서 사라지면 복구 경로가 끊긴다.
      - 사용 중 — 붙어 있는 사용자를 조용히 권한 없는 상태로 만들지 않는다.
        먼저 사용자에게서 역할을 떼게 하고, 그 행위를 각각 감사에 남긴다.
    """
    current = get_role(conn, role_cd)
    if current is None:
        raise RbacError(f"없는 역할입니다: {role_cd}")
    if role_cd in SYSTEM_ROLES:
        raise RbacError(f"시스템 역할은 삭제할 수 없습니다: {role_cd}")
    if current["user_cnt"] > 0:
        raise RbacError(
            f"이 역할을 쓰는 사용자가 {current['user_cnt']}명 있습니다. "
            "먼저 사용자에게서 역할을 해제하세요."
        )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM tw_role_permission WHERE role_cd = %s", (role_cd,))
        cur.execute("DELETE FROM tw_role WHERE role_cd = %s", (role_cd,))
    return current
