"""계약 상수 자기 정합성 단위 테스트.

권위: docs/contracts/db-contract.md

C-1 드리프트가 코드에서 재발하는 것을 막는다. 특히 §2.8 allowlist 와
§2.9 금지 목록이 겹치면 권한 설계가 자기모순이 된다.
"""

from __future__ import annotations

from lifelaw_web.db import contract


def test_allowlist_and_forbidden_lists_do_not_overlap() -> None:
    """쓸 수 있는 컬럼이 동시에 금지 컬럼일 수 없다."""
    for table, allowed in contract.WRITABLE_COLUMNS.items():
        overlap = allowed & contract.FORBIDDEN_UPDATE_COLUMNS
        assert not overlap, f"{table}: allowlist 와 금지 목록이 겹친다 {sorted(overlap)}"


def test_c1_drift_columns_are_in_forbidden_list() -> None:
    """C-1 에서 누락됐던 5개가 금지 목록에 있어야 한다.

    설계 v1.1 은 이 컬럼들을 빠뜨렸다. 재발하면 이 테스트가 잡는다.
    """
    for column in (
        "run_collect_policy_cd",
        "run_exclusion_site_policy_id",
        "run_exclusion_site_policy_version",
        "file_format_cd",
        "extract_method_cd",
    ):
        assert column in contract.FORBIDDEN_UPDATE_COLUMNS, column


def test_computed_columns_are_forbidden_for_write() -> None:
    for column in contract.GENERATED_COLUMNS:
        assert column in contract.FORBIDDEN_UPDATE_COLUMNS, column


def test_only_execution_column_depends_on_run_term() -> None:
    """effective 와 execution 의 차이는 run 항 하나뿐이다."""
    assert contract.GENERATED_COLUMNS["effective_collect_policy_cd"] is False
    assert contract.GENERATED_COLUMNS["execution_collect_policy_cd"] is True


def test_required_code_count_matches_ddl_seed() -> None:
    """DDL seed 는 34건이다. 33건으로 적었던 문서 오류가 재발하지 않게 고정한다."""
    assert contract.REQUIRED_CODE_COUNT == 34


def test_code_group_name_is_collect_target_kind() -> None:
    """그룹명은 COLLECT_TARGET_KIND 다. TARGET_KIND 가 아니다."""
    assert "COLLECT_TARGET_KIND" in contract.REQUIRED_CODES
    assert "TARGET_KIND" not in contract.REQUIRED_CODES


def test_baseline_code_is_in_change_yn_group() -> None:
    """5001 은 CHANGE_YN 그룹이며 변경 감지 집계에서 제외 대상이다."""
    assert contract.CHANGE_BASELINE_CODE in contract.REQUIRED_CODES["CHANGE_YN"]


def test_check_constraints_are_qualified_by_table() -> None:
    """파티션이 CHECK 제약을 복제하므로 이름만으로 세면 안 된다."""
    for table, conname in contract.REQUIRED_CHECK_CONSTRAINTS:
        assert table and conname
        assert table in {*contract.COLLECTOR_TABLES}


def test_append_only_tables_are_web_owned() -> None:
    for table in contract.APPEND_ONLY_TABLES:
        assert table.startswith("tw_"), table


def test_partitioned_table_is_a_collector_table() -> None:
    assert contract.PARTITIONED_TABLE in contract.COLLECTOR_TABLES


def test_ddl_pin_is_a_sha256_hex() -> None:
    assert len(contract.DDL_SHA256) == 64
    assert all(c in "0123456789abcdef" for c in contract.DDL_SHA256)
