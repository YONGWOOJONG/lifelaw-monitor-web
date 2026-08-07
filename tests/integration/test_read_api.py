"""조회 API 통합 테스트 — S-03 ~ S-17.

권위: DESIGN_admin_screen_inventory_v0_1.md

시드 데이터가 있어야 의미 있는 검증이 되므로, 없으면 skip 한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lifelaw_web.api.app import create_app
from lifelaw_web.auth import passwords
from lifelaw_web.query.paging import MAX_LIMIT
from lifelaw_web.rbac import permissions
from lifelaw_web.settings import Settings

pytestmark = pytest.mark.integration

PREFIX = "pytest_read_"
PASSWORD = "read-api-test-password"  # noqa: S105


@pytest.fixture(autouse=True)
def _require_seed(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tn_crawl_target")
        row = cur.fetchone()
    if not row or int(row[0]) == 0:
        pytest.skip("수집 데이터 없음 — scripts/db/seed/dev_seed.py 를 먼저 실행하세요")


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
                (PREFIX + login_id, f"조회 {login_id}", passwords.hash_password(PASSWORD)),
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


@pytest.fixture
def viewer(settings: Settings, make_user: Any) -> Iterator[TestClient]:
    make_user("viewer", [permissions.VIEWER])
    app = create_app(settings, verify_contract=False)
    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={"login_id": PREFIX + "viewer", "password": PASSWORD},
        )
        yield client


# ---------------------------------------------------------------------------
# 인가
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard",
        "/api/targets",
        "/api/targets/count",
        "/api/targets/1",
        "/api/targets/1/history",
        "/api/batch-runs",
        "/api/links",
        "/api/codes",
        "/api/site-policies",
    ],
)
def test_read_endpoints_require_authentication(settings: Settings, path: str) -> None:
    app = create_app(settings, verify_contract=False)
    with TestClient(app) as client:
        assert client.get(path).status_code == 401


def test_history_requires_its_own_permission(settings: Settings, make_user: Any) -> None:
    """target:history:read 는 target:read 와 별개 권한이다."""
    make_user("norole", [])
    app = create_app(settings, verify_contract=False)
    with TestClient(app) as client:
        client.post(
            "/api/auth/login", json={"login_id": PREFIX + "norole", "password": PASSWORD}
        )
        response = client.get("/api/targets/1/history")
        assert response.status_code == 403
        assert response.json()["required_permission"] == permissions.TARGET_HISTORY_READ


def test_site_policies_require_policy_read(settings: Settings, make_user: Any) -> None:
    make_user("norole2", [])
    app = create_app(settings, verify_contract=False)
    with TestClient(app) as client:
        client.post(
            "/api/auth/login", json={"login_id": PREFIX + "norole2", "password": PASSWORD}
        )
        response = client.get("/api/site-policies")
        assert response.status_code == 403
        assert response.json()["required_permission"] == permissions.POLICY_READ


# ---------------------------------------------------------------------------
# S-04 목록 · 페이징 · 정렬
# ---------------------------------------------------------------------------


def test_target_list_returns_page_envelope(viewer: TestClient) -> None:
    body = viewer.get("/api/targets", params={"limit": 10}).json()
    assert len(body["items"]) == 10
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert body["has_more"] is True


def test_target_list_paging_does_not_repeat_rows(viewer: TestClient) -> None:
    first = viewer.get("/api/targets", params={"limit": 20, "offset": 0}).json()["items"]
    second = viewer.get("/api/targets", params={"limit": 20, "offset": 20}).json()["items"]
    assert {r["url_id"] for r in first}.isdisjoint({r["url_id"] for r in second})


def test_last_page_reports_no_more(viewer: TestClient) -> None:
    total = viewer.get("/api/targets/count").json()["count"]
    body = viewer.get("/api/targets", params={"limit": 50, "offset": max(0, total - 1)}).json()
    assert body["has_more"] is False


def test_count_is_separate_from_the_list(viewer: TestClient) -> None:
    """전체 건수는 목록 응답에 들어 있지 않다(S-04 대용량 COUNT 회피)."""
    listing = viewer.get("/api/targets", params={"limit": 5}).json()
    assert "count" not in listing
    assert "total" not in listing
    assert viewer.get("/api/targets/count").json()["count"] >= 100


def test_limit_above_max_is_rejected(viewer: TestClient) -> None:
    assert viewer.get("/api/targets", params={"limit": MAX_LIMIT + 1}).status_code == 422


def test_every_row_carries_target_policy_version(viewer: TestClient) -> None:
    """S-09 일괄 변경의 입력이다. 없으면 낙관적 잠금을 걸 수 없다."""
    items = viewer.get("/api/targets", params={"limit": 50}).json()["items"]
    assert items
    assert all("target_policy_version" in row for row in items)


def test_rows_expose_both_computed_columns(viewer: TestClient) -> None:
    items = viewer.get("/api/targets", params={"limit": 50}).json()["items"]
    assert all("effective_collect_policy_cd" in row for row in items)
    assert all("execution_collect_policy_cd" in row for row in items)


def test_sort_key_allowlist_rejects_unknown_key(viewer: TestClient) -> None:
    """정렬 컬럼을 외부 입력으로 받지 않는다."""
    response = viewer.get("/api/targets", params={"sort": "url_id; DROP TABLE tw_user"})
    assert response.status_code == 400


def test_descending_sort_is_supported(viewer: TestClient) -> None:
    ascending = viewer.get("/api/targets", params={"sort": "url_id", "limit": 5}).json()
    descending = viewer.get("/api/targets", params={"sort": "-url_id", "limit": 5}).json()
    assert ascending["items"][0]["url_id"] < descending["items"][0]["url_id"]


# ---------------------------------------------------------------------------
# S-04 필터
# ---------------------------------------------------------------------------


def test_filter_by_crawl_state(viewer: TestClient) -> None:
    body = viewer.get("/api/targets", params={"crawl_stat_cd": "1090", "limit": MAX_LIMIT}).json()
    assert body["items"]
    assert all(row["crawl_stat_cd"] == "1090" for row in body["items"])


def test_filter_by_execution_policy_matches_count(viewer: TestClient) -> None:
    excluded = viewer.get("/api/targets/count", params={"execution_collect_policy_cd": "7020"})
    total = viewer.get("/api/targets/count")
    assert 0 < excluded.json()["count"] < total.json()["count"]


def test_filter_by_diagnostic_presence(viewer: TestClient) -> None:
    body = viewer.get(
        "/api/targets", params={"has_diagnostic": "true", "limit": MAX_LIMIT}
    ).json()
    assert body["items"]
    assert all(row["crawl_diag_cd"] in ("8010", "8020") for row in body["items"])


def test_filter_by_site_host(viewer: TestClient) -> None:
    policies = viewer.get("/api/site-policies")
    # VIEWER 는 policy:read 를 가지므로 통과해야 한다.
    assert policies.status_code == 200
    host = policies.json()["items"][0]["site_host"]
    body = viewer.get("/api/targets", params={"site_host": host, "limit": MAX_LIMIT}).json()
    assert all(row["site_host"] == host for row in body["items"])


# ---------------------------------------------------------------------------
# S-05 상세
# ---------------------------------------------------------------------------


def test_target_detail_includes_diagnostic_and_hashes(viewer: TestClient) -> None:
    diag = viewer.get(
        "/api/targets", params={"has_diagnostic": "true", "limit": 1}
    ).json()["items"][0]
    detail = viewer.get(f"/api/targets/{diag['url_id']}").json()
    assert detail["crawl_diag_cd"] in ("8010", "8020")
    assert detail["crawl_candidate_url"].startswith("https://")
    assert "prev_raw_hash" in detail


def test_unknown_target_is_404(viewer: TestClient) -> None:
    assert viewer.get("/api/targets/99999999").status_code == 404


# ---------------------------------------------------------------------------
# S-06 이력과 보존 범위
# ---------------------------------------------------------------------------


def test_history_reports_available_window(viewer: TestClient) -> None:
    """범위 밖의 0건이 유실이 아님을 화면이 구분할 수 있어야 한다(D-30)."""
    body = viewer.get("/api/targets/1/history").json()
    assert len(body["available_months"]) >= 2
    assert body["min_batch_ymd"] is not None
    assert body["max_batch_ymd"] is not None


def test_history_is_newest_first(viewer: TestClient) -> None:
    items = viewer.get("/api/targets/1/history", params={"limit": 20}).json()["items"]
    dates = [row["batch_ymd"] for row in items]
    assert dates == sorted(dates, reverse=True)


def test_history_outside_retention_is_empty_but_window_is_reported(viewer: TestClient) -> None:
    body = viewer.get("/api/targets/1/history", params={"batch_ymd_from": "20991201"}).json()
    assert body["items"] == []
    assert body["available_months"]


# ---------------------------------------------------------------------------
# S-10 · S-11 배치
# ---------------------------------------------------------------------------


def test_batch_run_list_and_detail(viewer: TestClient) -> None:
    listing = viewer.get("/api/batch-runs", params={"limit": 5}).json()
    assert listing["items"]
    run_id = listing["items"][0]["run_id"]
    detail = viewer.get(f"/api/batch-runs/{run_id}").json()
    assert detail["run_id"] == run_id
    assert detail["run_mode"] in ("fresh", "resume", "rerun")


def test_running_batches_have_no_end_time(viewer: TestClient) -> None:
    body = viewer.get("/api/batch-runs", params={"limit": MAX_LIMIT}).json()
    for row in body["items"]:
        if row["run_stat_cd"] in ("6010", "6020"):
            assert row["ended_at"] is None


def test_unknown_batch_run_is_404(viewer: TestClient) -> None:
    assert viewer.get("/api/batch-runs/99999999").status_code == 404


# ---------------------------------------------------------------------------
# S-16 · S-17 참조 데이터
# ---------------------------------------------------------------------------


def test_common_codes_are_read_only_and_complete(viewer: TestClient) -> None:
    items = viewer.get("/api/codes").json()["items"]
    assert len(items) == 34
    groups = {row["code_grp_cd"] for row in items}
    assert "COLLECT_TARGET_KIND" in groups
    assert "TARGET_KIND" not in groups
    # 라벨은 code_nm 이다. 프론트에 하드코딩하지 않는다.
    assert all(row["code_nm"] for row in items)


def test_common_codes_can_be_filtered_by_group(viewer: TestClient) -> None:
    items = viewer.get("/api/codes", params={"code_grp_cd": "CHANGE_YN"}).json()["items"]
    assert {row["code_val"] for row in items} == {
        "5000",
        "5001",
        "5010",
        "5020",
        "5030",
        "5040",
    }


def test_codes_endpoint_has_no_write_method(viewer: TestClient) -> None:
    """공통 코드 편집 경로를 제공하지 않는다(설계 §14)."""
    assert viewer.post("/api/codes", json={}).status_code in (403, 405)
    assert viewer.delete("/api/codes").status_code in (403, 405)


def test_link_master_is_listed_with_target_mapping(viewer: TestClient) -> None:
    body = viewer.get("/api/links", params={"limit": 10}).json()
    assert body["items"]
    row = body["items"][0]
    assert "con_link_seq" in row
    # url_id 와 con_link_seq 는 다른 식별자다. 시드가 일부러 다르게 만들었다.
    assert row["url_id"] != row["con_link_seq"]


# ---------------------------------------------------------------------------
# S-03 대시보드
# ---------------------------------------------------------------------------


def test_dashboard_excludes_baseline_from_change_count(viewer: TestClient) -> None:
    """5001(기준선 설정)을 변경 감지에 합산하지 않는다.

    합산하면 신규 대상이 대량 등록된 날 변경 건수가 폭증한 것처럼 보인다.
    """
    body = viewer.get("/api/dashboard").json()
    change_yn = body["change_yn"]
    expected = change_yn.get("5020", 0) + change_yn.get("5040", 0)
    assert body["change_detected_cnt"] == expected
    assert body["baseline_cnt"] == change_yn.get("5001", 0)
    assert body["baseline_cnt"] > 0
    assert body["change_detected_cnt"] != body["change_detected_cnt"] + body["baseline_cnt"]


def test_dashboard_reports_state_distributions(viewer: TestClient) -> None:
    body = viewer.get("/api/dashboard").json()
    assert body["total_targets"] >= 100
    assert set(body["crawl_stat"]) >= {"1010", "1020", "1090"}
    assert body["excluded_cnt"] > 0
    assert body["diagnostic_cnt"] > 0
    assert body["latest_runs"]


# ---------------------------------------------------------------------------
# 읽기 전용 보장
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/targets", "/api/batch-runs", "/api/links", "/api/site-policies", "/api/dashboard"],
)
def test_read_endpoints_reject_write_methods(viewer: TestClient, path: str) -> None:
    """3단계는 읽기 전용이다. 쓰기 경로가 열려 있으면 안 된다."""
    assert viewer.post(path, json={}).status_code in (403, 405)
    assert viewer.put(path, json={}).status_code in (403, 405)
    assert viewer.delete(path).status_code in (403, 405)
