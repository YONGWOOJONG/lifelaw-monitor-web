"""운영 현황 집계 — 화면 S-03.

권위: DESIGN_admin_screen_inventory_v0_1.md S-03
      docs/contracts/db-contract.md §2.6

┌──────────────────────────────────────────────────────────────────────────┐
│ 집계 규칙 (중요)                                                          │
│                                                                          │
│ `5001`(기준선 설정)은 신규 등록·강제 재기준선·성공 기준선 부재를 포함한다. │
│ **변경 감지 건수에 합산하지 않는다.** 합산하면 신규 대상이 대량 등록된 날  │
│ 변경 건수가 폭증한 것처럼 보인다.                                         │
└──────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from psycopg import sql

from lifelaw_web.db import contract

# 변경 "감지"로 세는 코드. 5001 은 여기 없다.
CHANGE_DETECTED_CODES: Final[tuple[str, ...]] = ("5020", "5040")
BASELINE_CODE: Final = contract.CHANGE_BASELINE_CODE  # "5001"

# 추이 카드가 보여줄 최대 업무일 수.
TREND_DAYS: Final = 14

# 실행 실패. 그 업무일의 0 건은 "변경이 없었다"가 아니라 "못 봤다"에 가깝다.
RUN_FAILED_CODE: Final = "6090"


@dataclass(frozen=True)
class ChangeTrendPoint:
    """업무일 하루치 변경 감지 수.

    `failed` 는 그 업무일의 배치가 실패(6090)했다는 뜻이다. 막대가 낮은 이유가
    "변경이 없어서"인지 "수집을 못 해서"인지 구분하지 못하면 추이를 잘못 읽는다.
    """

    batch_ymd: str
    change_detected_cnt: int
    failed: bool


@dataclass(frozen=True)
class Dashboard:
    batch_ymd: str | None
    total_targets: int
    crawl_stat: dict[str, int] = field(default_factory=dict)
    extract_stat: dict[str, int] = field(default_factory=dict)
    norm_stat: dict[str, int] = field(default_factory=dict)
    cmpr_stat: dict[str, int] = field(default_factory=dict)
    change_yn: dict[str, int] = field(default_factory=dict)
    change_detected_cnt: int = 0
    baseline_cnt: int = 0
    failed_cnt: int = 0
    excluded_cnt: int = 0
    diagnostic_cnt: int = 0
    latest_runs: list[dict[str, Any]] = field(default_factory=list)
    # None 은 "권한이 없어 집계하지 않았다"이고, [] 는 "조회 범위에 자료가 없다"다.
    # 화면이 둘을 같게 다루면 안 되므로 빈 리스트로 뭉개지 않는다.
    change_trend: list[ChangeTrendPoint] | None = None


# 집계 대상 상태 컬럼. 이 표의 값만 식별자로 SQL 에 들어간다.
_TALLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"crawl_stat_cd", "extract_stat_cd", "norm_stat_cd", "cmpr_stat_cd", "change_yn_cd"}
)


def _tally(conn: Any, column: str) -> dict[str, int]:
    """상태 코드 분포. 컬럼명은 allowlist 를 거쳐 Identifier 로만 합성한다."""
    if column not in _TALLY_COLUMNS:
        raise ValueError(f"집계 대상 컬럼이 아닙니다: {column}")
    statement = sql.SQL("SELECT {}, count(*) FROM tn_crawl_target GROUP BY 1").format(
        sql.Identifier(column)
    )
    with conn.cursor() as cur:
        cur.execute(statement)
        return {str(r[0]): int(r[1]) for r in cur.fetchall()}


def _change_trend(
    conn: Any,
    *,
    current_batch_ymd: str | None,
    current_change_detected: int,
    days: int = TREND_DAYS,
) -> list[ChangeTrendPoint]:
    """최근 업무일별 변경 감지 추이.

    출처가 두 곳인 이유:
      - 지난 업무일은 `TH_CRAWL_TARGET`(이력 스냅샷)에서 센다.
      - **오늘은 아직 이력에 없다.** 진행 중인 업무일의 판정은 작업 테이블
        (`TN_CRAWL_TARGET`)에만 있다. 그래서 오늘 막대는 이미 계산해 둔 헤드라인
        값을 그대로 재사용한다 — 따로 세면 같은 화면의 "변경 감지" 숫자와
        어긋날 수 있고, 그건 사용자가 가장 먼저 알아채는 종류의 버그다.

    `TH_CRAWL_TARGET` 을 읽으므로 **호출 측이 `target:history:read` 를 확인한
    뒤에만** 부른다(S-03 은 기본적으로 이 표의 사용처가 아니다).

    **빈 업무일을 0 으로 채우지 않는다.** 파티션 보존 범위 밖이라 자료가 없는
    날과 실제로 변경이 0 이었던 날은 다르다. 없는 날은 막대를 그리지 않는다.
    """
    codes = list(CHANGE_DETECTED_CODES)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT batch_ymd, count(*) FILTER (WHERE change_yn_cd = ANY(%s))
              FROM th_crawl_target
             GROUP BY batch_ymd
             ORDER BY batch_ymd DESC
             LIMIT %s
            """,
            (codes, days),
        )
        counts = {str(row[0]): int(row[1]) for row in cur.fetchall()}

    if current_batch_ymd:
        counts[current_batch_ymd] = current_change_detected

    if not counts:
        return []

    # 오늘을 더하면 days+1 이 될 수 있다. 오래된 쪽을 잘라 최신 days 일만 남긴다.
    ordered = sorted(counts)[-days:]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT batch_ymd FROM tn_batch_run "
            "WHERE run_stat_cd = %s AND batch_ymd = ANY(%s)",
            (RUN_FAILED_CODE, ordered),
        )
        failed = {str(row[0]) for row in cur.fetchall()}

    return [
        ChangeTrendPoint(
            batch_ymd=day,
            change_detected_cnt=counts[day],
            failed=day in failed,
        )
        for day in ordered
    ]


def build(conn: Any, *, include_trend: bool = False) -> Dashboard:
    """운영 현황 집계.

    `include_trend` 는 호출 측이 `target:history:read` 를 확인했다는 뜻이다.
    기본이 False 인 것은 fail-closed 를 위해서다 — 깜빡하면 카드가 빠질 뿐,
    권한 없는 사용자에게 이력 파생 자료가 새지는 않는다.
    """
    from psycopg.rows import dict_row

    with conn.cursor() as cur:
        cur.execute("SELECT count(*), max(batch_ymd) FROM tn_crawl_target")
        row = cur.fetchone()
        total = int(row[0]) if row else 0
        batch_ymd = str(row[1]) if row and row[1] else None

    change_yn = _tally(conn, "change_yn_cd")
    crawl_stat = _tally(conn, "crawl_stat_cd")

    # 변경 감지 = 5020 + 5040. 5001 은 더하지 않는다.
    change_detected = sum(change_yn.get(code, 0) for code in CHANGE_DETECTED_CODES)
    baseline = change_yn.get(BASELINE_CODE, 0)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE execution_collect_policy_cd = '7020'),
                   count(*) FILTER (WHERE crawl_diag_cd IS NOT NULL)
              FROM tn_crawl_target
            """
        )
        row = cur.fetchone()
        excluded = int(row[0]) if row else 0
        diagnostics = int(row[1]) if row else 0

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT run_id, batch_ymd, run_mode, run_stat_cd,
                   started_at, ended_at, total_cnt, change_detected_cnt
              FROM tn_batch_run
             ORDER BY batch_ymd DESC, run_id DESC
             LIMIT 5
            """
        )
        latest = [dict(r) for r in cur.fetchall()]

    failed = sum(
        crawl_stat.get(code, 0) for code in ("1090",)
    ) + sum(_tally(conn, "extract_stat_cd").get(code, 0) for code in ("2090",))

    trend = (
        _change_trend(
            conn,
            current_batch_ymd=batch_ymd,
            current_change_detected=change_detected,
        )
        if include_trend
        else None
    )

    return Dashboard(
        batch_ymd=batch_ymd,
        total_targets=total,
        crawl_stat=crawl_stat,
        extract_stat=_tally(conn, "extract_stat_cd"),
        norm_stat=_tally(conn, "norm_stat_cd"),
        cmpr_stat=_tally(conn, "cmpr_stat_cd"),
        change_yn=change_yn,
        change_detected_cnt=change_detected,
        baseline_cnt=baseline,
        failed_cnt=failed,
        excluded_cnt=excluded,
        diagnostic_cnt=diagnostics,
        latest_runs=latest,
        change_trend=trend,
    )
