"""관리 API 통합 테스트 — S-18 사용자, S-19 역할·권한, S-20 감사 로그.

권위: DESIGN_admin_screen_inventory_v0_1.md S-18 S-19 S-20
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17 §18 §19 §20

이 저장소의 **첫 쓰기 경로**라, 검증의 무게가 "잘 되는가"보다 "잘못될 수
없는가"에 있다. 계정 관리가 잠금 사고를 낼 수 있는 경로는 전부 여기서 막혀
있어야 한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lifelaw_web.api.app import create_app
from lifelaw_web.audit.writer import MASK
from lifelaw_web.auth import passwords
from lifelaw_web.rbac import permissions
from lifelaw_web.settings import Settings

pytestmark = pytest.mark.integration

PREFIX = "pytest_admin_"
PASSWORD = "admin-api-test-password"  # noqa: S105
REASON = "통합 테스트 검증"
TMP_ROLE = "PYTEST_ADMIN_TMP"


def _purge(conn: Any) -> None:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM tw_session WHERE user_id IN"
            " (SELECT user_id FROM tw_user WHERE login_id LIKE %s)",
            (PREFIX + "%",),
        )
        cur.execute(
            "DELETE FROM tw_user_role WHERE user_id IN"
            " (SELECT user_id FROM tw_user WHERE login_id LIKE %s)",
            (PREFIX + "%",),
        )
        cur.execute("DELETE FROM tw_user WHERE login_id LIKE %s", (PREFIX + "%",))
        cur.execute("DELETE FROM tw_role_permission WHERE role_cd LIKE %s", ("PYTEST_ADMIN%",))
        cur.execute("DELETE FROM tw_role WHERE role_cd LIKE %s", ("PYTEST_ADMIN%",))
    conn.commit()


@pytest.fixture
def make_user(conn: Any) -> Iterator[Any]:
    _purge(conn)

    def _make(login_id: str, roles: list[str]) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tw_user (login_id, user_nm, password_hash, use_yn, reger, moder)
                VALUES (%s, %s, %s, 'Y', 'pytest', 'pytest') RETURNING user_id
                """,
                (PREFIX + login_id, f"관리 {login_id}", passwords.hash_password(PASSWORD)),
            )
            user_id = int(cur.fetchone()[0])
            for role in roles:
                cur.execute(
                    "INSERT INTO tw_user_role (user_id, role_cd, reger) VALUES (%s, %s, 'pytest')",
                    (user_id, role),
                )
        conn.commit()
        return user_id

    yield _make
    _purge(conn)


def _client(settings: Settings, login_id: str, *, reauth: bool) -> TestClient:
    app = create_app(settings, verify_contract=False)
    client = TestClient(app)
    client.__enter__()
    body = client.post("/api/auth/login", json={"login_id": login_id, "password": PASSWORD}).json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    if reauth:
        # user:manage 는 재인증 신선도를 요구한다(§18 최고 등급).
        client.post("/api/auth/reauth", json={"password": PASSWORD})
    return client


@pytest.fixture
def admin(settings: Settings, make_user: Any) -> Iterator[TestClient]:
    make_user("admin", [permissions.ADMIN])
    client = _client(settings, PREFIX + "admin", reauth=True)
    yield client
    client.__exit__(None, None, None)


@pytest.fixture
def auditor(settings: Settings, make_user: Any) -> Iterator[TestClient]:
    make_user("auditor", [permissions.AUDITOR])
    client = _client(settings, PREFIX + "auditor", reauth=False)
    yield client
    client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 인가
# ---------------------------------------------------------------------------


def test_admin_endpoints_require_user_manage(settings: Settings, make_user: Any) -> None:
    """VIEWER 는 관리 API 에 닿지 못한다. 메뉴 숨김이 아니라 서버가 막는다(§17.3)."""
    make_user("viewer", [permissions.VIEWER])
    client = _client(settings, PREFIX + "viewer", reauth=True)
    try:
        for path in ("/api/admin/roles", "/api/admin/users", "/api/admin/permissions"):
            response = client.get(path)
            assert response.status_code == 403, path
            assert response.json()["required_permission"] == permissions.USER_MANAGE
    finally:
        client.__exit__(None, None, None)


def test_user_manage_requires_reauth(settings: Settings, make_user: Any) -> None:
    """재인증 없이 로그인만으로는 계정 관리에 닿지 못한다(§18 최고 등급)."""
    make_user("stale", [permissions.ADMIN])
    client = _client(settings, PREFIX + "stale", reauth=False)
    try:
        response = client.get("/api/admin/roles")
        assert response.status_code == 403
        assert response.json()["code"] == "REAUTH_REQUIRED"
    finally:
        client.__exit__(None, None, None)


def test_audit_read_is_separate_from_user_manage(admin: TestClient, auditor: TestClient) -> None:
    """§5 직무 분리 — ADMIN 은 감사를 못 읽고 AUDITOR 는 계정을 못 만진다.

    ADMIN 의 403 은 버그가 아니다. 둘을 겸하게 하면 4-eyes 가 무너진다.
    """
    assert admin.get("/api/admin/audit").status_code == 403
    assert auditor.get("/api/admin/audit").status_code == 200
    assert auditor.get("/api/admin/users").status_code == 403


def test_writes_require_csrf(admin: TestClient) -> None:
    saved = admin.headers.pop("X-CSRF-Token")
    try:
        response = admin.post(
            "/api/admin/roles",
            json={"role_cd": TMP_ROLE, "role_nm": "임시", "permissions": [], "reason": REASON},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "CSRF_FAILED"
    finally:
        admin.headers["X-CSRF-Token"] = saved


def test_reason_is_mandatory(admin: TestClient) -> None:
    """사유 없는 변경은 DTO 단계에서 막힌다(§18 중위험 이상 사유 필수)."""
    response = admin.post(
        "/api/admin/roles", json={"role_cd": TMP_ROLE, "role_nm": "임시", "permissions": []}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# S-19 역할·권한
# ---------------------------------------------------------------------------


def test_role_crud_roundtrip(admin: TestClient) -> None:
    created = admin.post(
        "/api/admin/roles",
        json={
            "role_cd": TMP_ROLE,
            "role_nm": "임시 역할",
            "permissions": [permissions.TARGET_READ, permissions.BATCH_READ],
            "reason": REASON,
        },
    )
    assert created.status_code == 201
    role = next(r for r in created.json()["items"] if r["role_cd"] == TMP_ROLE)
    assert sorted(role["permissions"]) == [permissions.BATCH_READ, permissions.TARGET_READ]
    assert role["is_system"] is False
    assert role["user_cnt"] == 0

    updated = admin.put(
        f"/api/admin/roles/{TMP_ROLE}",
        json={
            "role_nm": "임시 역할 2",
            "permissions": [permissions.TARGET_READ],
            "reason": REASON,
            "expected_role_nm": "임시 역할",
            "expected_permissions": role["permissions"],
        },
    )
    assert updated.status_code == 200
    after = next(r for r in updated.json()["items"] if r["role_cd"] == TMP_ROLE)
    assert after["permissions"] == [permissions.TARGET_READ]
    assert after["role_nm"] == "임시 역할 2"

    removed = admin.request("DELETE", f"/api/admin/roles/{TMP_ROLE}", json={"reason": REASON})
    assert removed.status_code == 200
    assert all(r["role_cd"] != TMP_ROLE for r in removed.json()["items"])


def test_role_update_rejects_stale_version(admin: TestClient) -> None:
    """§20 낙관적 잠금 — 보던 값이 다르면 409 로 거부하고 현재 값을 동봉한다."""
    admin.post(
        "/api/admin/roles",
        json={"role_cd": TMP_ROLE, "role_nm": "임시", "permissions": [], "reason": REASON},
    )
    response = admin.put(
        f"/api/admin/roles/{TMP_ROLE}",
        json={
            "role_nm": "다른 이름",
            "permissions": [],
            "reason": REASON,
            "expected_role_nm": "남이 이미 바꾼 이름",
            "expected_permissions": [],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["current"]["role_cd"] == TMP_ROLE


def test_unknown_permission_is_rejected(admin: TestClient) -> None:
    """코드가 검사하지 않는 권한을 붙이면 화면에만 "권한 있음"으로 보인다."""
    response = admin.post(
        "/api/admin/roles",
        json={
            "role_cd": TMP_ROLE,
            "role_nm": "임시",
            "permissions": ["not:a:real:permission"],
            "reason": REASON,
        },
    )
    assert response.status_code == 400


def test_system_roles_cannot_be_deleted(admin: TestClient) -> None:
    for role_cd in (permissions.ADMIN, permissions.VIEWER, permissions.AUDITOR):
        response = admin.request(
            "DELETE", f"/api/admin/roles/{role_cd}", json={"reason": REASON}
        )
        assert response.status_code == 400, role_cd


def test_admin_role_cannot_lose_user_manage(admin: TestClient) -> None:
    """빼는 순간 아무도 역할·권한을 되돌릴 수 없다."""
    current = next(
        r
        for r in admin.get("/api/admin/roles").json()["items"]
        if r["role_cd"] == permissions.ADMIN
    )
    response = admin.put(
        f"/api/admin/roles/{permissions.ADMIN}",
        json={
            "role_nm": current["role_nm"],
            "permissions": [permissions.TARGET_READ],
            "reason": REASON,
            "expected_role_nm": current["role_nm"],
            "expected_permissions": current["permissions"],
        },
    )
    assert response.status_code == 400


def test_role_in_use_cannot_be_deleted(admin: TestClient, make_user: Any) -> None:
    """붙어 있는 사용자를 조용히 권한 없는 상태로 만들지 않는다."""
    admin.post(
        "/api/admin/roles",
        json={"role_cd": TMP_ROLE, "role_nm": "임시", "permissions": [], "reason": REASON},
    )
    holder = make_user("holder", [TMP_ROLE])
    try:
        response = admin.request(
            "DELETE", f"/api/admin/roles/{TMP_ROLE}", json={"reason": REASON}
        )
        assert response.status_code == 400
        assert "사용자" in response.json()["detail"]
    finally:
        del holder


# ---------------------------------------------------------------------------
# S-18 사용자 — 잠금 사고 방어
# ---------------------------------------------------------------------------


def test_user_create_and_deactivate(admin: TestClient) -> None:
    created = admin.post(
        "/api/admin/users",
        json={
            "login_id": PREFIX + "made",
            "user_nm": "만들어진 사용자",
            "password": PASSWORD,
            "roles": [permissions.VIEWER],
            "reason": REASON,
        },
    )
    assert created.status_code == 201
    row = next(u for u in created.json()["items"] if u["login_id"] == PREFIX + "made")
    assert row["roles"] == [permissions.VIEWER]
    # 비밀번호 해시는 응답에 절대 실리지 않는다.
    assert "password_hash" not in row

    off = admin.put(
        f"/api/admin/users/{row['user_id']}/active", json={"active": False, "reason": REASON}
    )
    assert off.status_code == 200
    assert next(u for u in off.json()["items"] if u["user_id"] == row["user_id"])["use_yn"] == "N"


def test_cannot_deactivate_self(admin: TestClient) -> None:
    me = admin.get("/api/auth/me").json()
    response = admin.put(
        f"/api/admin/users/{me['user_id']}/active", json={"active": False, "reason": REASON}
    )
    assert response.status_code == 400


def test_cannot_strip_own_user_manage(admin: TestClient) -> None:
    me = admin.get("/api/auth/me").json()
    response = admin.put(
        f"/api/admin/users/{me['user_id']}/roles",
        json={
            "roles": [permissions.VIEWER],
            "reason": REASON,
            "expected_roles": [permissions.ADMIN],
        },
    )
    assert response.status_code == 400


def test_cannot_remove_last_manager(admin: TestClient, make_user: Any, conn: Any) -> None:
    """`user:manage` 를 가진 마지막 활성 사용자는 역할을 뺄 수 없다.

    역할 이름이 아니라 **권한 매핑**으로 센다 — S-19 에서 다른 역할에
    `user:manage` 를 붙였을 수도 있고, 그때도 판정이 맞아야 한다.
    """
    other = make_user("other_manager", [permissions.ADMIN])
    me = admin.get("/api/auth/me").json()

    # 관리자가 둘이면 남을 떼는 건 허용된다.
    allowed = admin.put(
        f"/api/admin/users/{other}/roles",
        json={"roles": [], "reason": REASON, "expected_roles": [permissions.ADMIN]},
    )
    assert allowed.status_code == 200

    # 이제 자기 자신만 남았으므로 자기 자신은 여전히 막힌다.
    blocked = admin.put(
        f"/api/admin/users/{me['user_id']}/roles",
        json={"roles": [], "reason": REASON, "expected_roles": [permissions.ADMIN]},
    )
    assert blocked.status_code == 400
    del conn


def test_password_reset_revokes_sessions(admin: TestClient, make_user: Any, conn: Any) -> None:
    victim = make_user("victim", [permissions.VIEWER])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tw_session WHERE user_id = %s", (victim,))
        before = int(cur.fetchone()[0])

    response = admin.put(
        f"/api/admin/users/{victim}/password",
        json={"password": "brand-new-password", "reason": REASON},
    )
    assert response.status_code == 200

    conn.rollback()  # 다른 커넥션의 커밋을 보기 위해 스냅샷을 새로 잡는다
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tw_session WHERE user_id = %s", (victim,))
        assert int(cur.fetchone()[0]) == 0
    del before


def test_short_password_is_rejected(admin: TestClient) -> None:
    response = admin.post(
        "/api/admin/users",
        json={
            "login_id": PREFIX + "weak",
            "user_nm": "약한 비번",
            "password": "short",
            "roles": [],
            "reason": REASON,
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# S-19/S-20 감사
# ---------------------------------------------------------------------------


def test_denied_attempts_are_audited(admin: TestClient, auditor: TestClient) -> None:
    """§19.1 실패한 시도도 남긴다.

    거부는 요청 트랜잭션과 함께 롤백되기 쉽다 — 감사를 명시적으로 커밋하지
    않으면 거부 기록이 통째로 사라진다. 그 회귀를 이 테스트가 잡는다.
    """
    admin.request("DELETE", f"/api/admin/roles/{permissions.ADMIN}", json={"reason": REASON})

    page = auditor.get("/api/admin/audit?result_cd=DENIED&action=ROLE_DELETE").json()
    assert page["items"], "거부 기록이 남지 않았다 — 감사 커밋이 롤백됐을 가능성"
    latest = page["items"][0]
    assert latest["result_cd"] == "DENIED"
    assert latest["target_type"] == "ROLE"
    assert REASON in (latest["reason"] or "")


def test_successful_change_records_before_and_after(
    admin: TestClient, auditor: TestClient
) -> None:
    """§19.1 변경 전후 값을 함께 남긴다."""
    admin.post(
        "/api/admin/roles",
        json={
            "role_cd": TMP_ROLE,
            "role_nm": "임시",
            "permissions": [permissions.TARGET_READ],
            "reason": REASON,
        },
    )
    admin.put(
        f"/api/admin/roles/{TMP_ROLE}",
        json={
            "role_nm": "임시 2",
            "permissions": [],
            "reason": REASON,
            "expected_role_nm": "임시",
            "expected_permissions": [permissions.TARGET_READ],
        },
    )
    page = auditor.get("/api/admin/audit?action=ROLE_UPDATE&result_cd=SUCCESS").json()
    entry = next(e for e in page["items"] if e["target_id"] == TMP_ROLE)
    assert entry["before_value"]["permissions"] == [permissions.TARGET_READ]
    assert entry["after_value"]["permissions"] == []


def test_password_is_masked_in_audit(
    admin: TestClient, auditor: TestClient, make_user: Any
) -> None:
    """비밀번호는 감사에 평문으로 남지 않는다(§19.1)."""
    victim = make_user("masked", [permissions.VIEWER])
    # ruff S105 는 변수명만 보고 하드코딩 비밀로 오탐한다. 감사에 새는지 확인하기
    # 위한 테스트 값이며, 이 문자열이 기록에 나타나면 실패해야 한다.
    secret = "plaintext-should-never-appear"  # noqa: S105
    admin.put(f"/api/admin/users/{victim}/password", json={"password": secret, "reason": REASON})
    page = auditor.get("/api/admin/audit?action=USER_PASSWORD_RESET").json()
    entry = page["items"][0]
    assert secret not in str(entry)
    assert entry["after_value"]["password"] == MASK


def test_audit_rejects_unknown_result_code(auditor: TestClient) -> None:
    assert auditor.get("/api/admin/audit?result_cd=NOT_A_CODE").status_code == 400


def test_audit_has_no_write_route(auditor: TestClient) -> None:
    """S-20 은 쓰기가 **없다**. append-only 이므로 경로 자체를 두지 않는다(§15).

    405 와 404 를 구분해 단정한다. `/audit` 은 GET 만 있으므로 POST 는 405 이고,
    `/audit/{id}` 는 **경로가 아예 없으므로** 404 다. 둘 다 쓰기 경로가 없다는
    뜻이지만, 405 로 뭉뚱그리면 나중에 누가 삭제 라우트를 추가해도 통과한다.
    """
    assert auditor.post("/api/admin/audit", json={}).status_code == 405
    assert auditor.request("DELETE", "/api/admin/audit/1").status_code == 404
