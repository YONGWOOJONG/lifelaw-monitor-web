"""개발 시드 데이터 품질 게이트.

권위 참고: scripts/db/seed/dev_seed.py

시드 데이터의 **상태 조합 자체는 가정**이지만(시드 스크립트 상단 경고 참조),
아래 불변식은 가정이 아니라 DDL 제약과 업무 의미에서 나오는 것이므로 어겨서는
안 된다. 시드를 다시 만들었을 때 품질이 떨어지는 것을 여기서 잡는다.

수집 데이터가 없으면 skip 한다.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration

CURRENT_BATCH_YMD = "20260806"


@pytest.fixture(autouse=True)
def _require_seed(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tn_crawl_target")
        row = cur.fetchone()
    if not row or int(row[0]) == 0:
        pytest.skip("수집 데이터 없음 — scripts/db/seed/dev_seed.py 를 먼저 실행하세요")


def scalar(conn: Any, sql: str, params: tuple[object, ...] = ()) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return row[0] if row else None


def test_history_has_no_future_business_dates(conn: Any) -> None:
    """이력은 지난 배치의 스냅샷이다. 미래 일자 행이 있으면 안 된다."""
    future = scalar(
        conn, "SELECT count(*) FROM th_crawl_target WHERE batch_ymd > %s", (CURRENT_BATCH_YMD,)
    )
    assert int(future) == 0


def test_history_spans_multiple_partitions(conn: Any) -> None:
    """S-06 이력 화면과 파티션 프루닝을 검증할 수 있어야 한다."""
    partitions = scalar(
        conn,
        """
        SELECT count(DISTINCT tableoid) FROM th_crawl_target
        """,
    )
    assert int(partitions) >= 2


def test_run_only_exclusion_is_represented(conn: Any) -> None:
    """effective 와 execution 이 다른 행이 있어야 한다.

    이 구분을 화면에서 혼용하면 "제외인데 제외가 아닌" 표시가 나온다.
    구분을 검증할 데이터가 없으면 그 버그를 잡을 수 없다.
    """
    count = scalar(
        conn,
        """
        SELECT count(*) FROM tn_crawl_target
         WHERE effective_collect_policy_cd <> execution_collect_policy_cd
        """,
    )
    assert int(count) > 0


def test_generated_columns_match_the_or_rule(conn: Any) -> None:
    """계산 컬럼이 DDL 수식대로 산출되는지 데이터로 재확인한다."""
    mismatched = scalar(
        conn,
        """
        SELECT count(*) FROM tn_crawl_target
         WHERE effective_collect_policy_cd <> CASE
                 WHEN site_collect_policy_cd = '7020'
                   OR target_collect_policy_cd = '7020' THEN '7020' ELSE '7010' END
            OR execution_collect_policy_cd <> CASE
                 WHEN site_collect_policy_cd = '7020'
                   OR target_collect_policy_cd = '7020'
                   OR run_collect_policy_cd = '7020' THEN '7020' ELSE '7010' END
        """,
    )
    assert int(mismatched) == 0


def test_diagnostic_rows_satisfy_all_five_conditions(conn: Any) -> None:
    """ck_crawl_target_diag 는 3컬럼 all-or-none 이 아니라 5조건 결합이다."""
    bad = scalar(
        conn,
        """
        SELECT count(*) FROM tn_crawl_target
         WHERE crawl_diag_cd IS NOT NULL
           AND NOT (crawl_diag_cd IN ('8010','8020')
                    AND btrim(crawl_diag_msg) <> ''
                    AND crawl_candidate_url LIKE 'https://%%'
                    AND crawl_stat_cd = '1090'
                    AND change_yn_cd = '5000')
        """,
    )
    assert int(bad) == 0
    present = scalar(conn, "SELECT count(*) FROM tn_crawl_target WHERE crawl_diag_cd IS NOT NULL")
    assert int(present) > 0, "진단 코드 행이 없으면 S-05 진단 표시를 검증할 수 없다"


def test_target_kind_matches_link_class(conn: Any) -> None:
    """ck_crawl_target_direct_kind: 7110↔901001, 7120↔901002, NULL↔target 7010."""
    bad = scalar(
        conn,
        """
        SELECT count(*) FROM tn_crawl_target
         WHERE NOT (
               (collect_target_kind_cd IS NULL AND target_collect_policy_cd = '7010')
            OR (collect_target_kind_cd = '7110' AND link_class_cd = '901001')
            OR (collect_target_kind_cd = '7120' AND link_class_cd = '901002'))
        """,
    )
    assert int(bad) == 0


def test_all_crawl_states_are_represented(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT crawl_stat_cd FROM tn_crawl_target")
        states = {str(r[0]) for r in cur.fetchall()}
    assert {"1010", "1020", "1090"} <= states


def test_baseline_code_is_present_and_distinguishable(conn: Any) -> None:
    """5001 기준선 설정이 있어야 '변경 감지 집계에서 제외' 규칙을 검증할 수 있다."""
    baseline = int(scalar(conn, "SELECT count(*) FROM tn_crawl_target WHERE change_yn_cd = '5001'"))
    changed = int(
        scalar(conn, "SELECT count(*) FROM tn_crawl_target WHERE change_yn_cd IN ('5020','5040')")
    )
    assert baseline > 0
    assert changed > 0


def test_unchanged_rows_have_matching_baseline_hashes(conn: Any) -> None:
    """5010/5030(변경 없음)은 기준선 해시와 같아야 의미가 맞는다."""
    bad = scalar(
        conn,
        """
        SELECT count(*) FROM tn_crawl_target
         WHERE change_yn_cd IN ('5010','5030')
           AND (raw_html_hash IS DISTINCT FROM prev_raw_hash)
        """,
    )
    assert int(bad) == 0


def test_batch_ledger_covers_modes_and_states(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT run_mode FROM tn_batch_run")
        modes = {str(r[0]) for r in cur.fetchall()}
        cur.execute("SELECT DISTINCT run_stat_cd FROM tn_batch_run")
        states = {str(r[0]) for r in cur.fetchall()}
    assert {"fresh", "resume", "rerun"} <= modes
    assert {"6010", "6020", "6030"} <= states


def test_running_and_pending_runs_have_no_end_time(conn: Any) -> None:
    bad = scalar(
        conn,
        """
        SELECT count(*) FROM tn_batch_run
         WHERE run_stat_cd IN ('6010','6020') AND ended_at IS NOT NULL
        """,
    )
    assert int(bad) == 0


def test_paging_dataset_is_large_enough(conn: Any) -> None:
    """S-04 목록 페이징과 §20.2 일괄 변경 상한(200건)을 검증할 만큼 있어야 한다."""
    targets = int(scalar(conn, "SELECT count(*) FROM tn_crawl_target"))
    history = int(scalar(conn, "SELECT count(*) FROM th_crawl_target"))
    assert targets >= 100
    assert history >= 300


def test_site_policies_cover_both_codes(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT collect_policy_cd FROM tn_collect_site_policy")
        codes = {str(r[0]) for r in cur.fetchall()}
    assert codes == {"7010", "7020"}


def test_seed_urls_use_reserved_domains_only(conn: Any) -> None:
    """실제 사이트를 수집 대상으로 만들지 않는다(RFC 2606/6761 예약 도메인만)."""
    bad = scalar(
        conn,
        """
        SELECT count(*) FROM tn_crawl_target
         WHERE con_link_url NOT LIKE 'https://%%.example.test/%%'
           AND con_link_url NOT LIKE 'https://%%.example.invalid/%%'
        """,
    )
    assert int(bad) == 0
