"""개발 전용 수집 데이터 시드.

권위 참고: docs/contracts/db-contract.md (제약·코드값)
           docs/runbooks/dev-database-setup.md RB-6

┌─────────────────────────────────────────────────────────────────────────────┐
│ 경고 — 이 데이터의 상태 조합은 **가정**이다.                                 │
│                                                                             │
│ 수집기(lifelaw-monitor)가 실제로 만들어내는 상태 조합의 권위 있는 정의는     │
│ R2/R3/R5/R6/R7 이며, 이 스크립트는 그것을 재현하지 않는다. DDL 제약을        │
│ 만족하는 "그럴듯한" 조합을 만들어 **화면 개발과 성능 검증**에 쓰는 것이       │
│ 목적이다.                                                                    │
│                                                                             │
│ 따라서:                                                                      │
│  - 이 데이터를 수집기 동작의 근거로 인용하지 않는다                          │
│  - 상태 전이 로직을 이 데이터에 맞추지 않는다                                │
│  - 실제 수집 결과를 확보하면 이 시드를 폐기하고 그것을 쓴다                  │
└─────────────────────────────────────────────────────────────────────────────┘

성격:
  - **개발 전용 도구.** 운영에 배포하지 않는다.
  - 수집기 소유 테이블(TN_/TH_)에 쓰므로 Web 런타임 롤로는 동작하지 않는다.
    이것은 설계대로다(계약 §2.9). DB 소유자 권한으로 실행한다.
  - 결정적(deterministic)이다. 난수를 쓰지 않으므로 같은 입력에 같은 결과가
    나오고, 테스트가 흔들리지 않는다.

사용:
    LIFELAW_WEB_SEED_CONFIRM=yes \
    LIFELAW_WEB_SEED_DB_USER=postgres \
    LIFELAW_WEB_SEED_DB_PASSWORD=... \
    .venv/Scripts/python.exe scripts/db/seed/dev_seed.py [--reset]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from lifelaw_web.settings import SettingsError, load_config

ENV_CONFIRM: Final = "LIFELAW_WEB_SEED_CONFIRM"
ENV_USER: Final = "LIFELAW_WEB_SEED_DB_USER"
ENV_PASSWORD: Final = "LIFELAW_WEB_SEED_DB_PASSWORD"  # noqa: S105

# TH 파티션이 존재하는 업무월만 쓴다. 밖의 일자는 파티션 부재로 거부된다.
BATCH_MONTHS: Final[tuple[str, ...]] = ("202606", "202607", "202608")
CURRENT_BATCH_YMD: Final = "20260806"

WEB_CLASS: Final = "901001"
FILE_CLASS: Final = "901002"
KIND_WEB: Final = "7110"
KIND_PDF: Final = "7120"
POLICY_COLLECT: Final = "7010"
POLICY_EXCLUDE: Final = "7020"


class SeedError(RuntimeError):
    """중단 조건."""


# ---------------------------------------------------------------------------
# 시드 사양
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteSpec:
    host: str
    policy: str
    reason: str | None


# 정규화된 host. RFC 2606/6761 예약 도메인만 쓴다. 실제 사이트를 넣지 않는다.
SITES: Final[tuple[SiteSpec, ...]] = (
    SiteSpec("law.example.test", POLICY_COLLECT, None),
    SiteSpec("welfare.example.test", POLICY_COLLECT, None),
    SiteSpec("tax.example.test", POLICY_COLLECT, None),
    SiteSpec("housing.example.test", POLICY_COLLECT, None),
    SiteSpec("labor.example.test", POLICY_COLLECT, None),
    SiteSpec("archive.example.test", POLICY_EXCLUDE, "보존 종료 사이트 — 수집 제외"),
    SiteSpec("mirror.example.invalid", POLICY_EXCLUDE, "미러 사이트 — 중복 수집 방지"),
    SiteSpec("legacy.example.invalid", POLICY_EXCLUDE, "폐쇄 예정 — 수집 제외"),
)


@dataclass(frozen=True)
class Scenario:
    """DDL 제약을 만족하는 상태 조합 하나."""

    key: str
    link_class: str
    crawl: str
    extract: str
    norm: str
    cmpr: str
    change: str
    has_raw_hash: bool
    has_norm_hash: bool
    has_prev_hash: bool
    crawl_err: str | None = None
    extract_err: str | None = None
    norm_err: str | None = None
    diag: str | None = None  # 8010 / 8020 — CHECK 가 crawl=1090, change=5000 을 요구


SCENARIOS: Final[tuple[Scenario, ...]] = (
    # ── 웹페이지 (901001) ──────────────────────────────────────────────────
    Scenario("web-wait", WEB_CLASS, "1010", "2010", "3010", "4010", "5000", False, False, False),
    Scenario("web-baseline", WEB_CLASS, "1020", "2020", "3020", "4020", "5001", True, True, False),
    Scenario("web-unchanged", WEB_CLASS, "1020", "2020", "3020", "4020", "5010", True, True, True),
    Scenario(
        "web-raw-changed", WEB_CLASS, "1020", "2020", "3020", "4020", "5020", True, True, True
    ),
    Scenario(
        "web-crawl-fail",
        WEB_CLASS,
        "1090",
        "2010",
        "3010",
        "4010",
        "5000",
        False,
        False,
        True,
        crawl_err="HTTP 503 Service Unavailable",
    ),
    Scenario(
        "web-diag-https",
        WEB_CLASS,
        "1090",
        "2010",
        "3010",
        "4010",
        "5000",
        False,
        False,
        True,
        crawl_err="HTTP 404 Not Found",
        diag="8010",
    ),
    Scenario(
        "web-diag-relocated",
        WEB_CLASS,
        "1090",
        "2010",
        "3010",
        "4010",
        "5000",
        False,
        False,
        True,
        crawl_err="HTTP 301 Moved Permanently",
        diag="8020",
    ),
    Scenario(
        "web-extract-fail",
        WEB_CLASS,
        "1020",
        "2090",
        "3010",
        "4010",
        "5000",
        True,
        False,
        True,
        extract_err="본문 컨테이너를 찾지 못했습니다",
    ),
    Scenario(
        "web-norm-fail",
        WEB_CLASS,
        "1020",
        "2020",
        "3090",
        "4010",
        "5000",
        True,
        False,
        True,
        norm_err="style 제거 중 파싱 오류",
    ),
    # ── 첨부파일 / PDF (901002) ────────────────────────────────────────────
    Scenario("pdf-wait", FILE_CLASS, "1010", "2000", "3000", "4000", "5000", False, False, False),
    Scenario("pdf-baseline", FILE_CLASS, "1020", "2020", "3020", "4020", "5001", True, True, False),
    Scenario(
        "pdf-detail-unchanged",
        FILE_CLASS,
        "1020",
        "2020",
        "3020",
        "4020",
        "5030",
        True,
        True,
        True,
    ),
    Scenario(
        "pdf-detail-changed", FILE_CLASS, "1020", "2020", "3020", "4020", "5040", True, True, True
    ),
    Scenario(
        "pdf-raw-changed", FILE_CLASS, "1020", "2020", "3020", "4020", "5020", True, True, True
    ),
    Scenario(
        "pdf-crawl-fail",
        FILE_CLASS,
        "1090",
        "2000",
        "3000",
        "4000",
        "5000",
        False,
        False,
        True,
        crawl_err="파일 크기 상한 초과",
    ),
)

# 제외 변형. 인덱스 주기로 섞는다.
EXCL_NONE: Final = "none"
EXCL_SITE: Final = "site"  # 사이트 상속 제외
EXCL_TARGET: Final = "target"  # 대상 직접 제외
EXCL_RUN: Final = "run"  # 실행 중 redirect 제외

EXCLUSION_CYCLE: Final[tuple[str, ...]] = (
    EXCL_NONE,
    EXCL_NONE,
    EXCL_NONE,
    EXCL_NONE,
    EXCL_NONE,
    EXCL_SITE,
    EXCL_NONE,
    EXCL_TARGET,
    EXCL_NONE,
    EXCL_RUN,
)

TARGET_COUNT: Final = 120
CON_LINK_BASE: Final = 1000


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TargetRow:
    url_id: int
    con_link_seq: int
    host: str
    site_policy_id: int | None
    url: str
    scenario: Scenario
    exclusion: str
    site_policy: str
    site_policy_version: int
    target_policy: str
    target_kind: str | None
    target_policy_version: int
    run_policy: str
    run_excl_site_policy_id: int | None
    run_excl_site_policy_version: int

    @property
    def effective_policy(self) -> str:
        if POLICY_EXCLUDE in (self.site_policy, self.target_policy):
            return POLICY_EXCLUDE
        return POLICY_COLLECT

    @property
    def execution_policy(self) -> str:
        if POLICY_EXCLUDE in (self.site_policy, self.target_policy, self.run_policy):
            return POLICY_EXCLUDE
        return POLICY_COLLECT


def build_targets(site_policy_ids: dict[str, int]) -> list[TargetRow]:
    """결정적으로 대상 목록을 만든다. 난수를 쓰지 않는다."""
    rows: list[TargetRow] = []
    for index in range(TARGET_COUNT):
        site = SITES[index % len(SITES)]
        scenario = SCENARIOS[index % len(SCENARIOS)]
        exclusion = EXCLUSION_CYCLE[index % len(EXCLUSION_CYCLE)]

        url_id = index + 1
        con_link_seq = CON_LINK_BASE + url_id
        suffix = "pdf" if scenario.link_class == FILE_CLASS else "html"
        url = f"https://{site.host}/notice/{url_id:04d}.{suffix}"

        # 사이트 상속. ck_crawl_target_site_binding:
        #   site_policy_id NULL  -> site_collect_policy_cd='7010' AND version=0
        #   site_policy_id 있음  -> version>=1
        site_is_excluded = site.policy == POLICY_EXCLUDE or exclusion == EXCL_SITE
        if site_is_excluded:
            site_policy_id: int | None = site_policy_ids[site.host]
            site_policy = POLICY_EXCLUDE
            site_policy_version = 1
        else:
            site_policy_id = None
            site_policy = POLICY_COLLECT
            site_policy_version = 0

        # 대상 직접 정책. ck_crawl_target_direct_kind:
        #   kind NULL -> target='7010'
        #   kind 7110 -> link_class 901001 / 7120 -> 901002
        if exclusion == EXCL_TARGET:
            target_policy = POLICY_EXCLUDE
            target_kind: str | None = (
                KIND_WEB if scenario.link_class == WEB_CLASS else KIND_PDF
            )
            target_policy_version = 1
        else:
            target_policy = POLICY_COLLECT
            target_kind = None
            target_policy_version = 0

        # 실행 중 제외. ck_crawl_target_run_exclusion:
        #   '7010' -> id NULL AND version=0
        #   '7020' -> id NOT NULL AND version>=1
        if exclusion == EXCL_RUN:
            run_policy = POLICY_EXCLUDE
            run_excl_id: int | None = site_policy_ids["mirror.example.invalid"]
            run_excl_version = 1
        else:
            run_policy = POLICY_COLLECT
            run_excl_id = None
            run_excl_version = 0

        rows.append(
            TargetRow(
                url_id=url_id,
                con_link_seq=con_link_seq,
                host=site.host,
                site_policy_id=site_policy_id,
                url=url,
                scenario=scenario,
                exclusion=exclusion,
                site_policy=site_policy,
                site_policy_version=site_policy_version,
                target_policy=target_policy,
                target_kind=target_kind,
                target_policy_version=target_policy_version,
                run_policy=run_policy,
                run_excl_site_policy_id=run_excl_id,
                run_excl_site_policy_version=run_excl_version,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# 삽입
# ---------------------------------------------------------------------------


def insert_sites(cur: psycopg.Cursor[Any]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for site in SITES:
        cur.execute(
            """
            INSERT INTO tn_collect_site_policy
                (site_host, collect_policy_cd, policy_version, policy_reason, reger, moder)
            VALUES (%s, %s, 1, %s, 'dev_seed', 'dev_seed')
            RETURNING site_policy_id
            """,
            (site.host, site.policy, site.reason),
        )
        row = cur.fetchone()
        if row is None:
            raise SeedError(f"사이트 정책 INSERT 실패: {site.host}")
        ids[site.host] = int(row[0])
    return ids


def insert_links(cur: psycopg.Cursor[Any], targets: list[TargetRow]) -> None:
    cur.executemany(
        """
        INSERT INTO tn_cnpcls_cnlnk
            (con_link_seq, con_link_nm, con_link_class_cd, con_link_url,
             lk_insp_dt, reger, reg_dt, moder, mod_dt)
        VALUES (%s, %s, %s, %s, now(), 'dev_seed', now(), 'dev_seed', now())
        """,
        [
            (
                t.con_link_seq,
                f"{t.host} 고시 {t.url_id:04d}",
                t.scenario.link_class,
                t.url,
            )
            for t in targets
        ],
    )


def insert_targets(cur: psycopg.Cursor[Any], targets: list[TargetRow]) -> None:
    """계산 컬럼(effective/execution)은 INSERT 목록에서 제외한다.

    GENERATED ALWAYS 컬럼에 값을 넣으면 SQLSTATE 428C9 로 거부된다.
    """
    payload = []
    for t in targets:
        s = t.scenario
        raw_hash = sha256_hex(f"raw:{t.url_id}") if s.has_raw_hash else None
        norm_hash = sha256_hex(f"norm:{t.url_id}") if s.has_norm_hash else None
        if s.has_prev_hash:
            # 5010/5030 은 변경 없음이므로 기준선과 같은 해시여야 의미가 맞는다.
            same = s.change in ("5010", "5030")
            prev_raw = raw_hash if same and raw_hash else sha256_hex(f"prev-raw:{t.url_id}")
            prev_norm = norm_hash if same and norm_hash else sha256_hex(f"prev-norm:{t.url_id}")
        else:
            prev_raw = prev_norm = None

        # ck_crawl_target_diag: 3컬럼 all-or-none 이면서
        #   diag_cd IN ('8010','8020') AND diag_msg 비어있지 않음
        #   AND candidate_url LIKE 'https://%' AND crawl_stat_cd='1090'
        #   AND change_yn_cd='5000'
        if s.diag:
            diag_cd: str | None = s.diag
            diag_msg: str | None = (
                "HTTPS 전환 후보 확인" if s.diag == "8010" else "URL 이전 후보 확인"
            )
            candidate: str | None = f"https://{t.host}/notice/{t.url_id:04d}-moved.html"
        else:
            diag_cd = diag_msg = candidate = None

        is_file = s.link_class == FILE_CLASS
        payload.append(
            (
                t.url_id,
                t.con_link_seq,
                t.url,
                s.link_class,
                t.site_policy_id,
                t.target_kind,
                t.site_policy,
                t.target_policy,
                t.site_policy_version,
                t.target_policy_version,
                t.run_policy,
                t.run_excl_site_policy_id,
                t.run_excl_site_policy_version,
                CURRENT_BATCH_YMD,
                s.crawl,
                s.crawl_err,
                diag_cd,
                diag_msg,
                candidate,
                raw_hash,
                (12_345 + t.url_id * 17) if s.has_raw_hash else None,
                s.extract,
                s.extract_err,
                ("PDF_TEXT" if is_file else "HTML_MAIN") if s.extract == "2020" else None,
                s.norm,
                s.norm_err,
                norm_hash,
                s.cmpr,
                s.change,
                ("PDF" if is_file else "HTML") if s.has_raw_hash else None,
                prev_raw,
                prev_norm,
            )
        )

    cur.executemany(
        """
        INSERT INTO tn_crawl_target (
            url_id, con_link_seq, con_link_url, link_class_cd,
            site_policy_id, collect_target_kind_cd,
            site_collect_policy_cd, target_collect_policy_cd,
            site_policy_version, target_policy_version,
            run_collect_policy_cd, run_exclusion_site_policy_id,
            run_exclusion_site_policy_version,
            batch_ymd, crawl_stat_cd, crawl_err_msg,
            crawl_diag_cd, crawl_diag_msg, crawl_candidate_url,
            raw_html_hash, file_size,
            extract_stat_cd, extract_err_msg, extract_method_cd,
            norm_stat_cd, norm_err_msg, norm_html_hash,
            cmpr_stat_cd, change_yn_cd, file_format_cd,
            prev_raw_hash, prev_norm_hash
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        """,
        payload,
    )


def history_dates() -> list[str]:
    """파티션이 있는 3개월 안에서 결정적으로 날짜를 고른다.

    **현재 업무일자를 넘는 날짜는 만들지 않는다.** 이력은 이미 지난 배치의
    스냅샷이므로 미래 일자 행이 있으면 화면이 존재할 수 없는 데이터를 보여준다.
    """
    days = ("05", "12", "19", "26")
    dates = [f"{month}{day}" for month in BATCH_MONTHS for day in days]
    return [ymd for ymd in dates if ymd <= CURRENT_BATCH_YMD]


def insert_history(cur: psycopg.Cursor[Any], targets: list[TargetRow]) -> int:
    """TH 스냅샷. effective/execution 은 GENERATED 가 아니므로 직접 계산해 넣는다.

    ck_h_crawl_target_config_policy / ck_h_crawl_target_execution_effective 가
    같은 수식을 CHECK 로 강제하므로 계산이 틀리면 INSERT 가 거부된다.
    """
    dates = history_dates()
    payload = []
    for t in targets:
        s = t.scenario
        # 대상마다 다른 개수의 이력을 남긴다(1~12건). 결정적이다.
        count = 1 + (t.url_id % len(dates))
        for ymd in dates[:count]:
            has_result = s.crawl != "1010"
            diag_cd = s.diag
            payload.append(
                (
                    t.url_id,
                    ymd,
                    t.con_link_seq,
                    t.url,
                    s.link_class,
                    t.site_policy_id,
                    t.target_kind,
                    t.site_policy,
                    t.target_policy,
                    t.effective_policy,
                    t.site_policy_version,
                    t.target_policy_version,
                    t.run_policy,
                    t.run_excl_site_policy_id,
                    t.run_excl_site_policy_version,
                    t.execution_policy,
                    s.crawl if has_result else None,
                    s.crawl_err,
                    diag_cd,
                    ("HTTPS 전환 후보 확인" if diag_cd == "8010" else "URL 이전 후보 확인")
                    if diag_cd
                    else None,
                    f"https://{t.host}/notice/{t.url_id:04d}-moved.html" if diag_cd else None,
                    s.extract if has_result else None,
                    s.norm if has_result else None,
                    s.cmpr if has_result else None,
                    s.change if has_result else None,
                    sha256_hex(f"raw:{t.url_id}:{ymd}") if s.has_raw_hash else None,
                    sha256_hex(f"norm:{t.url_id}:{ymd}") if s.has_norm_hash else None,
                    ("PDF" if s.link_class == FILE_CLASS else "HTML") if s.has_raw_hash else None,
                )
            )

    cur.executemany(
        """
        INSERT INTO th_crawl_target (
            url_id, batch_ymd, con_link_seq, con_link_url, link_class_cd,
            site_policy_id, collect_target_kind_cd,
            site_collect_policy_cd, target_collect_policy_cd,
            effective_collect_policy_cd,
            site_policy_version, target_policy_version,
            run_collect_policy_cd, run_exclusion_site_policy_id,
            run_exclusion_site_policy_version, execution_collect_policy_cd,
            crawl_stat_cd, crawl_err_msg,
            crawl_diag_cd, crawl_diag_msg, crawl_candidate_url,
            extract_stat_cd, norm_stat_cd, cmpr_stat_cd, change_yn_cd,
            raw_html_hash, norm_html_hash, file_format_cd
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        payload,
    )
    return len(payload)


def insert_batch_runs(cur: psycopg.Cursor[Any]) -> int:
    """배치 실행 원장. fresh/resume/rerun 과 전 상태 코드를 섞는다."""
    runs = [
        # (batch_ymd, run_mode, run_stat_cd, total, success, fail, changed, err, excluded)
        ("20260605", "fresh", "6030", 118, 112, 6, 9, 6, 24),
        ("20260612", "fresh", "6040", 118, 100, 18, 7, 18, 24),
        ("20260619", "fresh", "6030", 118, 115, 3, 4, 3, 24),
        ("20260626", "fresh", "6090", 118, 40, 78, 1, 78, 24),
        ("20260626", "rerun", "6030", 118, 116, 2, 5, 2, 24),
        ("20260705", "fresh", "6030", 119, 117, 2, 3, 2, 24),
        ("20260712", "fresh", "6080", 119, 55, 0, 2, 0, 24),
        ("20260712", "resume", "6030", 119, 118, 1, 6, 1, 24),
        ("20260719", "fresh", "6030", 119, 119, 0, 0, 0, 24),
        ("20260726", "fresh", "6040", 119, 104, 15, 8, 15, 24),
        ("20260805", "fresh", "6030", 120, 118, 2, 11, 2, 24),
        (CURRENT_BATCH_YMD, "fresh", "6020", 120, 74, 3, 5, 3, 24),
        (CURRENT_BATCH_YMD, "resume", "6010", 120, 0, 0, 0, 0, 24),
    ]
    cur.executemany(
        """
        INSERT INTO tn_batch_run (
            batch_ymd, run_mode, run_stat_cd, started_at, ended_at,
            total_cnt, success_cnt, fail_cnt, change_detected_cnt,
            err_cnt, excluded_cnt
        ) VALUES (
            %s, %s, %s,
            (%s::date + time '02:00')::timestamptz,
            CASE WHEN %s IN ('6010','6020') THEN NULL
                 ELSE (%s::date + time '05:30')::timestamptz END,
            %s, %s, %s, %s, %s, %s
        )
        """,
        [
            (ymd, mode, stat, ymd, stat, ymd, total, ok, fail, changed, err, excl)
            for ymd, mode, stat, total, ok, fail, changed, err, excl in runs
        ],
    )
    return len(runs)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def reset(cur: psycopg.Cursor[Any]) -> None:
    """시드 데이터를 지운다. 개발 DB 전용."""
    cur.execute("DELETE FROM th_crawl_target")
    cur.execute("DELETE FROM tn_crawl_target")
    cur.execute("DELETE FROM tn_cnpcls_cnlnk")
    cur.execute("DELETE FROM tn_batch_run")
    cur.execute("DELETE FROM tn_collect_site_policy")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SeedError(f"환경변수 {name} 가 없습니다.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="개발 전용 수집 데이터 시드")
    parser.add_argument("--reset", action="store_true", help="기존 시드를 지우고 다시 넣는다")
    args = parser.parse_args(argv)

    try:
        if os.environ.get(ENV_CONFIRM) != "yes":
            raise SeedError(
                f"{ENV_CONFIRM}=yes 가 필요합니다. 이 도구는 개발 DB 전용이며 "
                "수집기 소유 테이블에 씁니다."
            )
        config = load_config()
        user = require_env(ENV_USER)
        password = require_env(ENV_PASSWORD)
        pg = config.postgres

        with psycopg.connect(
            host=pg.host,
            port=pg.port,
            dbname=pg.database,
            user=user,
            password=password,
            options="-c timezone=Asia/Seoul",
            autocommit=False,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM tn_crawl_target")
                row = cur.fetchone()
                existing = int(row[0]) if row else 0
                if existing and not args.reset:
                    raise SeedError(
                        f"tn_crawl_target 에 이미 {existing}건이 있습니다. "
                        "--reset 을 주면 지우고 다시 넣습니다."
                    )
                if args.reset:
                    reset(cur)

                site_ids = insert_sites(cur)
                targets = build_targets(site_ids)
                insert_links(cur, targets)
                insert_targets(cur, targets)
                history_rows = insert_history(cur, targets)
                run_rows = insert_batch_runs(cur)
            conn.commit()
    except SeedError as exc:
        print(f"중단: {exc}", file=sys.stderr)
        return 2
    except (SettingsError, psycopg.Error) as exc:
        detail = getattr(exc, "sqlstate", None)
        print(
            f"실패: {type(exc).__name__}" + (f" sqlstate={detail}" if detail else ""),
            file=sys.stderr,
        )
        return 3

    print(
        f"시드 완료 | 사이트 {len(SITES)} | 링크·대상 {len(targets)} "
        f"| 이력 {history_rows} | 배치 {run_rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
