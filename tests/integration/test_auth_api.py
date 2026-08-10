"""인증·RBAC·감사 API 통합 테스트.

권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3 §17.4 §18 §19

실제 DB 를 쓴다. 테스트가 만든 계정·세션·감사 행은 끝에서 정리한다.
부트스트랩 계정(user_id=1)은 건드리지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lifelaw_web.api.app import create_app
from lifelaw_web.api.security import CSRF_HEADER
from lifelaw_web.auth import passwords
from lifelaw_web.rbac import permissions
from lifelaw_web.settings import Settings

pytestmark = pytest.mark.integration

TEST_PREFIX = "pytest_"
TEST_PASSWORD = "correct-horse-battery-staple"  # noqa: S105 - 테스트 전용 값
WRONG_PASSWORD = "wrong-password"  # noqa: S105


def _purge_test_rows(conn: Any) -> None:
    """pytest_ 접두사 계정과 세션을 지운다.

    추적한 id 만 지우면 이전 실행이 중간에 실패했을 때 잔재가 남아 다음 실행이
    UNIQUE 위반으로 깨진다. 접두사 기준으로 지워 그 상황을 자체 복구한다.

    **감사 행은 지우지 않는다.** 런타임 롤에 DELETE 권한이 없기 때문이며, 그것이
    설계대로다(§15). 테스트가 남긴 감사 행은 개발 DB 에 누적된다. 조회는 actor
    접두사로 걸러내므로 누적이 검증을 방해하지 않는다.
    """
    conn.rollback()  # 앞선 실패로 트랜잭션이 중지돼 있을 수 있다
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM tw_session WHERE user_id IN
                (SELECT user_id FROM tw_user WHERE login_id LIKE %s)
            """,
            (TEST_PREFIX + "%",),
        )
        cur.execute(
            """
            DELETE FROM tw_user_role WHERE user_id IN
                (SELECT user_id FROM tw_user WHERE login_id LIKE %s)
            """,
            (TEST_PREFIX + "%",),
        )
        cur.execute("DELETE FROM tw_user WHERE login_id LIKE %s", (TEST_PREFIX + "%",))
    conn.commit()


@pytest.fixture
def make_user(conn: Any) -> Iterator[Any]:
    """테스트 계정을 만들고 끝나면 지운다."""
    _purge_test_rows(conn)

    def _make(login_id: str, roles: list[str], *, use_yn: str = "Y") -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tw_user (login_id, user_nm, password_hash, use_yn, reger, moder)
                VALUES (%s, %s, %s, %s, 'pytest', 'pytest')
                RETURNING user_id
                """,
                (
                    TEST_PREFIX + login_id,
                    f"테스트 {login_id}",
                    passwords.hash_password(TEST_PASSWORD),
                    use_yn,
                ),
            )
            row = cur.fetchone()
            user_id = int(row[0])
            for role in roles:
                cur.execute(
                    "INSERT INTO tw_user_role (user_id, role_cd, reger) VALUES (%s, %s, 'pytest')",
                    (user_id, role),
                )
        conn.commit()
        return user_id

    yield _make

    _purge_test_rows(conn)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, verify_contract=False)
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, login_id: str, password: str = TEST_PASSWORD) -> Any:
    return client.post(
        "/api/auth/login",
        json={"login_id": TEST_PREFIX + login_id, "password": password},
    )


# ---------------------------------------------------------------------------
# 로그인
# ---------------------------------------------------------------------------


def test_login_succeeds_and_sets_httponly_cookie(
    client: TestClient, make_user: Any, settings: Settings
) -> None:
    make_user("viewer", [permissions.VIEWER])
    response = login(client, "viewer")

    assert response.status_code == 200
    body = response.json()
    assert body["principal"]["login_id"] == TEST_PREFIX + "viewer"
    assert body["csrf_token"]

    cookie_name = settings.config.session.cookie_name
    set_cookie = response.headers["set-cookie"]
    assert cookie_name in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie
    assert "SameSite=lax" in set_cookie.lower().replace("samesite=lax", "SameSite=lax")


def test_login_response_never_contains_password_or_hash(
    client: TestClient, make_user: Any
) -> None:
    make_user("nohash", [permissions.VIEWER])
    raw = login(client, "nohash").text
    assert TEST_PASSWORD not in raw
    assert "argon2" not in raw
    assert "password" not in raw


def test_login_with_wrong_password_is_401(client: TestClient, make_user: Any) -> None:
    make_user("wrongpw", [permissions.VIEWER])
    response = login(client, "wrongpw", WRONG_PASSWORD)
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_unknown_account_and_wrong_password_are_indistinguishable(
    client: TestClient, make_user: Any
) -> None:
    """계정 존재 여부가 응답으로 새어나가면 안 된다."""
    make_user("known", [permissions.VIEWER])
    wrong = login(client, "known", WRONG_PASSWORD)
    unknown = login(client, "does-not-exist", TEST_PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_disabled_account_cannot_log_in(client: TestClient, make_user: Any) -> None:
    make_user("disabled", [permissions.VIEWER], use_yn="N")
    assert login(client, "disabled").status_code == 401


def test_repeated_failures_lock_the_account(
    client: TestClient, make_user: Any, settings: Settings, conn: Any
) -> None:
    """잠긴 뒤에는 올바른 비밀번호도 거부된다."""
    make_user("lockme", [permissions.VIEWER])
    for _ in range(settings.config.session.max_failed_logins):
        assert login(client, "lockme", WRONG_PASSWORD).status_code == 401

    assert login(client, "lockme").status_code == 401

    with conn.cursor() as cur:
        cur.execute(
            "SELECT failed_login_cnt, locked_until FROM tw_user WHERE login_id = %s",
            (TEST_PREFIX + "lockme",),
        )
        row = cur.fetchone()
    assert int(row[0]) >= settings.config.session.max_failed_logins
    assert row[1] is not None


def test_successful_login_resets_failure_counter(
    client: TestClient, make_user: Any, conn: Any
) -> None:
    make_user("resetme", [permissions.VIEWER])
    login(client, "resetme", WRONG_PASSWORD)
    assert login(client, "resetme").status_code == 200
    with conn.cursor() as cur:
        cur.execute(
            "SELECT failed_login_cnt, last_login_at FROM tw_user WHERE login_id = %s",
            (TEST_PREFIX + "resetme",),
        )
        row = cur.fetchone()
    assert int(row[0]) == 0
    assert row[1] is not None


# ---------------------------------------------------------------------------
# 세션과 권한 재조회
# ---------------------------------------------------------------------------


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_me_returns_permissions_from_roles(client: TestClient, make_user: Any) -> None:
    make_user("policy", [permissions.POLICY_MANAGER])
    login(client, "policy")
    body = client.get("/api/auth/me").json()
    granted = set(body["permissions"])
    assert permissions.POLICY_SITE_WRITE in granted
    assert permissions.TARGET_READ in granted
    assert permissions.USER_MANAGE not in granted


def test_permission_revocation_takes_effect_without_relogin(
    client: TestClient, make_user: Any, conn: Any
) -> None:
    """권한은 매 요청 재조회한다. 로그인 시점 스냅샷을 신뢰하지 않는다."""
    user_id = make_user("revoke", [permissions.AUDITOR])
    login(client, "revoke")
    assert permissions.AUDIT_READ in client.get("/api/auth/me").json()["permissions"]

    with conn.cursor() as cur:
        cur.execute("DELETE FROM tw_user_role WHERE user_id = %s", (user_id,))
    conn.commit()

    assert client.get("/api/auth/me").json()["permissions"] == []


def test_disabling_account_invalidates_live_session(
    client: TestClient, make_user: Any, conn: Any
) -> None:
    user_id = make_user("killme", [permissions.VIEWER])
    login(client, "killme")
    assert client.get("/api/auth/me").status_code == 200

    with conn.cursor() as cur:
        cur.execute("UPDATE tw_user SET use_yn = 'N' WHERE user_id = %s", (user_id,))
    conn.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_logout_destroys_the_server_session(client: TestClient, make_user: Any) -> None:
    make_user("logout", [permissions.VIEWER])
    csrf = login(client, "logout").json()["csrf_token"]

    assert client.post("/api/auth/logout", headers={CSRF_HEADER: csrf}).status_code == 204
    # 쿠키가 남아 있어도 서버 세션이 없으므로 거부된다.
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# CSRF 와 Origin
# ---------------------------------------------------------------------------


def test_state_changing_request_without_csrf_token_is_403(
    client: TestClient, make_user: Any
) -> None:
    make_user("nocsrf", [permissions.VIEWER])
    login(client, "nocsrf")
    response = client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"


def test_state_changing_request_with_wrong_csrf_token_is_403(
    client: TestClient, make_user: Any
) -> None:
    make_user("badcsrf", [permissions.VIEWER])
    login(client, "badcsrf")
    response = client.post("/api/auth/logout", headers={CSRF_HEADER: "not-the-token"})
    assert response.status_code == 403


def test_me_returns_the_csrf_token_so_a_reload_can_recover(
    client: TestClient, make_user: Any
) -> None:
    """새로고침 뒤에도 CSRF 토큰을 되찾을 수 있어야 한다.

    회귀 방지. 토큰이 로그인 응답에만 있던 판에서는, 새로고침하면 브라우저
    메모리의 토큰만 사라지고 세션 쿠키는 남았다. 화면은 로그인 상태로 보이는데
    모든 상태 변경이 `CSRF_FAILED` 로 막혔고, **재인증도 POST 라 회복 경로가
    없었다.** 실제로 "비밀번호가 맞는데 CSRF 오류"로 보고된 증상이다.
    """
    make_user("reload", [permissions.ADMIN])
    login_body = login(client, "reload").json()

    # 클라이언트가 토큰을 잃은 상태를 흉내낸다 — 쿠키만 남기고 /me 로 복구한다.
    me = client.get("/api/auth/me").json()
    assert "csrf_token" in me, "/me 가 토큰을 내리지 않으면 새로고침을 복구할 수 없다"

    # 저장이 아니라 유도이므로 세션 수명 동안 같은 값이다. 탭을 여러 개 열어도
    # 서로의 토큰을 무효화하지 않는다.
    assert me["csrf_token"] == login_body["csrf_token"]

    # 그 토큰만으로 재인증이 통과해야 한다. 여기가 막히면 최고 위험 작업이
    # 통째로 잠긴다.
    reauth = client.post(
        "/api/auth/reauth",
        json={"password": TEST_PASSWORD},
        headers={CSRF_HEADER: me["csrf_token"]},
    )
    assert reauth.status_code == 200
    assert reauth.json()["csrf_token"] == me["csrf_token"]


def test_csrf_token_is_not_stored_in_plaintext(
    conn: Any, client: TestClient, make_user: Any
) -> None:
    """유도로 바꿨어도 **저장은 여전히 해시**다.

    토큰을 다시 계산할 수 있게 만든 것이 곧 평문 보관을 뜻하지는 않는다.
    """
    make_user("hashed", [permissions.VIEWER])
    token = login(client, "hashed").json()["csrf_token"]
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tw_session WHERE csrf_token_hash = %s", (token,))
        assert int(cur.fetchone()[0]) == 0


def test_read_request_does_not_need_csrf_token(client: TestClient, make_user: Any) -> None:
    make_user("readonly", [permissions.VIEWER])
    login(client, "readonly")
    assert client.get("/api/auth/me").status_code == 200


def test_disallowed_origin_is_rejected(client: TestClient, make_user: Any) -> None:
    make_user("origin", [permissions.VIEWER])
    response = client.post(
        "/api/auth/login",
        json={"login_id": TEST_PREFIX + "origin", "password": TEST_PASSWORD},
        headers={"Origin": "https://evil.example.invalid"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"


def test_allowed_origin_passes(client: TestClient, make_user: Any, settings: Settings) -> None:
    make_user("goodorigin", [permissions.VIEWER])
    origin = settings.config.allowed_origins[0]
    response = client.post(
        "/api/auth/login",
        json={"login_id": TEST_PREFIX + "goodorigin", "password": TEST_PASSWORD},
        headers={"Origin": origin},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 재인증과 권한 게이트
# ---------------------------------------------------------------------------


def test_contract_status_requires_permission(client: TestClient, make_user: Any) -> None:
    """AUDITOR 는 batch:read 를 갖고 있으므로 통과해야 한다."""
    make_user("auditor", [permissions.AUDITOR])
    login(client, "auditor")
    response = client.get("/api/status/contract")
    assert response.status_code == 200
    assert response.json()["all_passed"] is True


def test_contract_status_denied_without_role(client: TestClient, make_user: Any) -> None:
    make_user("norole", [])
    login(client, "norole")
    response = client.get("/api/status/contract")
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert response.json()["required_permission"] == permissions.BATCH_READ


def test_reauth_marks_session_and_is_audited(
    client: TestClient, make_user: Any, conn: Any
) -> None:
    make_user("reauth", [permissions.ADMIN])
    csrf = login(client, "reauth").json()["csrf_token"]
    assert client.get("/api/auth/me").json()["session"]["reauth_fresh"] is False

    response = client.post(
        "/api/auth/reauth",
        json={"password": TEST_PASSWORD},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 200
    assert response.json()["session"]["reauth_fresh"] is True

    with conn.cursor() as cur:
        cur.execute(
            "SELECT result_cd FROM tw_audit_log WHERE actor = %s AND action = 'REAUTH'",
            (TEST_PREFIX + "reauth",),
        )
        results = {str(r[0]) for r in cur.fetchall()}
    assert "SUCCESS" in results


def test_reauth_with_wrong_password_is_401_and_audited(
    client: TestClient, make_user: Any, conn: Any
) -> None:
    make_user("badreauth", [permissions.ADMIN])
    csrf = login(client, "badreauth").json()["csrf_token"]
    response = client.post(
        "/api/auth/reauth",
        json={"password": WRONG_PASSWORD},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 401

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM tw_audit_log WHERE actor = %s AND result_cd = 'DENIED'",
            (TEST_PREFIX + "badreauth",),
        )
        assert int(cur.fetchone()[0]) >= 1


# ---------------------------------------------------------------------------
# 감사
# ---------------------------------------------------------------------------


def test_failed_login_is_audited(client: TestClient, make_user: Any, conn: Any) -> None:
    """실패한 시도도 남긴다(설계 §19.1)."""
    make_user("auditfail", [permissions.VIEWER])
    login(client, "auditfail", WRONG_PASSWORD)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT result_cd, after_value FROM tw_audit_log
             WHERE actor = %s AND action = 'LOGIN'
            """,
            (TEST_PREFIX + "auditfail",),
        )
        rows = cur.fetchall()
    assert any(str(r[0]) == "DENIED" for r in rows)


def test_audit_rows_never_contain_the_password(
    client: TestClient, make_user: Any, conn: Any
) -> None:
    make_user("auditmask", [permissions.VIEWER])
    login(client, "auditmask")
    login(client, "auditmask", WRONG_PASSWORD)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT coalesce(before_value::text, '') || coalesce(after_value::text, '')
              FROM tw_audit_log WHERE actor = %s
            """,
            (TEST_PREFIX + "auditmask",),
        )
        blob = "".join(str(r[0]) for r in cur.fetchall())
    assert TEST_PASSWORD not in blob
    assert WRONG_PASSWORD not in blob
    assert "argon2" not in blob


def test_audit_log_cannot_be_deleted_by_the_runtime_role(conn: Any) -> None:
    """감사 로그는 append-only 다. 애플리케이션 규율이 아니라 DB 가 막는다.

    이 테스트는 정리 코드가 실제로 막혀서 발견한 성질을 고정한 것이다.
    """
    import psycopg

    with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM tw_audit_log WHERE actor = 'never-exists'")
    conn.rollback()


def test_security_headers_are_present(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
