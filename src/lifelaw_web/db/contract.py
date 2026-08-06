"""DB 계약 상수 — 코드 상의 단일 출처.

권위: docs/contracts/db-contract.md
      DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7 §21

이 모듈의 값은 `docs/contracts/db-contract.md`와 일치해야 한다. 문서가 개정되면
여기도 함께 바꾼다. 반대로 여기만 바꾸고 문서를 두면 C-1과 같은 드리프트가
다시 생긴다.

**컬럼 소유권을 판단할 때 설계 문서 요약이 아니라 이 모듈과 계약 문서를 본다.**
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# 계약 버전 핀 (db-contract.md §1)
# ---------------------------------------------------------------------------

C1_DOC_VERSION: Final = "2.20"
G1_DOC_VERSION: Final = "3.14"
DDL_FILENAME: Final = "create_c_schema_v2_19.sql"
DDL_SHA256: Final = "3b8fbfa14fa396b4e75996558aad2e18c6fd2c0007501d3bef37f49bfc7db9fa"

# 이 코드가 기대하는 TW_ 마이그레이션 버전. 불일치 시 기동을 실패시킨다.
EXPECTED_MIGRATION_VERSION: Final = "0001"

# ---------------------------------------------------------------------------
# 수집기 소유 테이블 (db-contract.md §2.1)
# ---------------------------------------------------------------------------

COLLECTOR_TABLES: Final[tuple[str, ...]] = (
    "tc_common_code",
    "tn_collect_site_policy",
    "tn_cnpcls_cnlnk",
    "tn_crawl_target",
    "th_crawl_target",
    "tn_batch_run",
)

PARTITIONED_TABLE: Final = "th_crawl_target"

# ---------------------------------------------------------------------------
# 계산 컬럼 (db-contract.md §2.2)
#
# TN 에서는 GENERATED ALWAYS ... STORED 이고, TH 에서는 일반 컬럼 + CHECK 강제다.
# 두 컬럼의 차이는 run_collect_policy_cd 항 하나뿐이다.
# ---------------------------------------------------------------------------

GENERATED_COLUMNS: Final[dict[str, bool]] = {
    # 컬럼명 -> 수식에 run_collect_policy_cd 항이 있어야 하는가
    "effective_collect_policy_cd": False,
    "execution_collect_policy_cd": True,
}

# ---------------------------------------------------------------------------
# 쓰기 allowlist (db-contract.md §2.8)
#
# 이 목록 밖의 컬럼에 대한 UPDATE 경로를 만들지 않는다.
# target_collect_policy_cd 와 collect_target_kind_cd 는 DDL 제약
# ck_crawl_target_direct_kind 때문에 항상 같은 문장에서 함께 갱신해야 한다.
# ---------------------------------------------------------------------------

WRITABLE_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "tn_crawl_target": frozenset(
        {
            "target_collect_policy_cd",
            "collect_target_kind_cd",
            "target_policy_version",
            "mod_dt",
        }
    ),
    "tn_collect_site_policy": frozenset(
        {
            "collect_policy_cd",
            "policy_version",
            "policy_reason",
            "moder",
            "mod_dt",
        }
    ),
}

# ---------------------------------------------------------------------------
# 절대 쓰지 않는 컬럼 (db-contract.md §2.9)
#
# v1.1 설계는 run_* 3개와 file_format_cd, extract_method_cd 를 누락했다(C-1).
# 이 목록이 완전한 목록이다.
# ---------------------------------------------------------------------------

FORBIDDEN_UPDATE_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        # 실행 상태
        "crawl_stat_cd",
        "extract_stat_cd",
        "norm_stat_cd",
        "cmpr_stat_cd",
        "change_yn_cd",
        # 오류
        "crawl_err_msg",
        "extract_err_msg",
        "norm_err_msg",
        "cmpr_err_msg",
        "change_err_msg",
        # 해시
        "raw_html_hash",
        "norm_html_hash",
        "prev_raw_hash",
        "prev_norm_hash",
        # 진단
        "crawl_diag_cd",
        "crawl_diag_msg",
        "crawl_candidate_url",
        # 파일·방법
        "file_size",
        "file_mtime",
        "file_format_cd",
        "extract_method_cd",
        # 일자
        "batch_ymd",
        # 실행 제외 (C-1 에서 추가)
        "run_collect_policy_cd",
        "run_exclusion_site_policy_id",
        "run_exclusion_site_policy_version",
        # 사이트 상속
        "site_policy_id",
        "site_collect_policy_cd",
        "site_policy_version",
        # 계산 컬럼
        "effective_collect_policy_cd",
        "execution_collect_policy_cd",
    }
)

# ---------------------------------------------------------------------------
# 의존 코드값 (db-contract.md §2.6) — DDL seed 기준 34건
#
# 그룹명은 COLLECT_TARGET_KIND 다 (TARGET_KIND 가 아니다).
# 5001(기준선 설정)은 변경 감지 건수에 합산하지 않는다.
# ---------------------------------------------------------------------------

REQUIRED_CODES: Final[dict[str, tuple[str, ...]]] = {
    "CRAWL_STAT": ("1010", "1020", "1090"),
    "EXTRACT_STAT": ("2000", "2010", "2020", "2090"),
    "NORM_STAT": ("3000", "3010", "3020", "3090"),
    "CMPR_STAT": ("4000", "4010", "4020"),
    "CHANGE_YN": ("5000", "5001", "5010", "5020", "5030", "5040"),
    "RUN_STAT": ("6010", "6020", "6030", "6040", "6080", "6090"),
    "COLLECT_POLICY": ("7010", "7020"),
    "COLLECT_TARGET_KIND": ("7110", "7120"),
    "CRAWL_DIAG": ("8010", "8020"),
    "LINK_CLASS": ("901001", "901002"),
}

REQUIRED_CODE_COUNT: Final = sum(len(v) for v in REQUIRED_CODES.values())

# 변경 감지 건수 집계에서 제외해야 하는 코드 (기준선 설정).
CHANGE_BASELINE_CODE: Final = "5001"

# ---------------------------------------------------------------------------
# CHECK 제약 (db-contract.md §2.3)
#
# 파티션은 부모의 CHECK 제약을 복제한다. 반드시 대상 테이블과 함께 확인한다.
# ---------------------------------------------------------------------------

REQUIRED_CHECK_CONSTRAINTS: Final[tuple[tuple[str, str], ...]] = (
    ("tn_crawl_target", "ck_crawl_target_site_binding"),
    ("tn_crawl_target", "ck_crawl_target_direct_kind"),
    ("tn_crawl_target", "ck_crawl_target_run_exclusion"),
    ("tn_crawl_target", "ck_crawl_target_diag"),
    ("tn_collect_site_policy", "ck_collect_site_policy"),
    ("tn_collect_site_policy", "ck_collect_site_version"),
    ("th_crawl_target", "ck_h_crawl_target_diag"),
)

# ---------------------------------------------------------------------------
# append-only 테이블 (설계 §15, §19)
#
# 런타임 롤이 UPDATE/DELETE 권한을 가지면 기동을 실패시킨다.
# 애플리케이션 규율만으로는 부족하다.
# ---------------------------------------------------------------------------

APPEND_ONLY_TABLES: Final[tuple[str, ...]] = (
    "tw_audit_log",
    "tw_approval",
)
