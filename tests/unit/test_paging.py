"""페이징·정렬 단위 테스트.

권위: DESIGN_admin_screen_inventory_v0_1.md S-04
      DESIGN_project_structure_and_toolchain_v0_1.md §3

DB 를 쓰지 않는다. 정렬 키가 SQL 로 흘러들지 않는지를 여기서 고정한다.
"""

from __future__ import annotations

import pytest
from psycopg import sql

from lifelaw_web.query import batches, reference
from lifelaw_web.query import targets as targets_query
from lifelaw_web.query.paging import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_OFFSET,
    PageParams,
    SortError,
    build_page,
    order_by,
)

ALLOWLIST = {"url_id": ("t", "url_id"), "mod_dt": ("t", "mod_dt")}


def rendered(fragment: sql.Composable) -> str:
    return fragment.as_string(None)


# ---------------------------------------------------------------------------
# 페이징
# ---------------------------------------------------------------------------


def test_limit_is_clamped_to_max() -> None:
    assert PageParams(limit=10_000).normalised().limit == MAX_LIMIT


def test_limit_below_one_is_clamped() -> None:
    assert PageParams(limit=0).normalised().limit == 1
    assert PageParams(limit=-5).normalised().limit == 1


def test_offset_is_clamped() -> None:
    assert PageParams(offset=-1).normalised().offset == 0
    assert PageParams(offset=MAX_OFFSET * 10).normalised().offset == MAX_OFFSET


def test_default_limit_is_conservative() -> None:
    assert PageParams().limit == DEFAULT_LIMIT
    assert DEFAULT_LIMIT < MAX_LIMIT


def test_build_page_detects_more_rows() -> None:
    params = PageParams(limit=3, offset=0)
    page = build_page([1, 2, 3, 4], params)
    assert page.items == [1, 2, 3]
    assert page.has_more is True


def test_build_page_on_last_page() -> None:
    page = build_page([1, 2], PageParams(limit=3, offset=0))
    assert page.items == [1, 2]
    assert page.has_more is False


def test_build_page_on_empty_result() -> None:
    page = build_page([], PageParams(limit=10, offset=0))
    assert page.items == []
    assert page.has_more is False


# ---------------------------------------------------------------------------
# 정렬 allowlist
# ---------------------------------------------------------------------------


def test_known_key_produces_quoted_identifier() -> None:
    assert rendered(order_by("url_id", ALLOWLIST, "url_id")) == '"t"."url_id" ASC'


def test_descending_prefix_is_honoured() -> None:
    assert rendered(order_by("-mod_dt", ALLOWLIST, "url_id")) == '"t"."mod_dt" DESC'


def test_default_is_used_when_key_is_absent() -> None:
    assert rendered(order_by(None, ALLOWLIST, "url_id")) == '"t"."url_id" ASC'


@pytest.mark.parametrize(
    "attack",
    [
        "url_id; DROP TABLE tw_user",
        "url_id, (SELECT password_hash FROM tw_user)",
        "1",
        "t.url_id",
        "*",
        "url_id--",
        "-",
    ],
)
def test_unknown_or_malicious_keys_are_rejected(attack: str) -> None:
    """사용자 문자열은 키 조회에만 쓰이고 SQL 에 들어가지 않는다."""
    with pytest.raises(SortError):
        order_by(attack, ALLOWLIST, "url_id")


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_sort_means_unspecified(blank: str | None) -> None:
    """`?sort=` 처럼 비어 있는 값은 오류가 아니라 기본 정렬이다."""
    assert rendered(order_by(blank, ALLOWLIST, "url_id")) == '"t"."url_id" ASC'


def test_rejected_key_is_echoed_without_reaching_sql() -> None:
    with pytest.raises(SortError) as exc:
        order_by("evil", ALLOWLIST, "url_id")
    assert "evil" in str(exc.value)


# ---------------------------------------------------------------------------
# 실제 모듈의 allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("allowlist", "default"),
    [
        (targets_query.SORT_ALLOWLIST, targets_query.DEFAULT_SORT),
        (batches.SORT_ALLOWLIST, batches.DEFAULT_SORT),
        (reference.LINK_SORT_ALLOWLIST, reference.LINK_DEFAULT_SORT),
    ],
)
def test_module_defaults_resolve(allowlist: dict[str, tuple[str, ...]], default: str) -> None:
    assert rendered(order_by(default, allowlist, default))


@pytest.mark.parametrize(
    "allowlist",
    [
        targets_query.SORT_ALLOWLIST,
        batches.SORT_ALLOWLIST,
        reference.LINK_SORT_ALLOWLIST,
    ],
)
def test_allowlist_values_are_plain_identifier_parts(
    allowlist: dict[str, tuple[str, ...]],
) -> None:
    """allowlist 값에 SQL 조각이 섞이면 Identifier 인용이 무의미해진다."""
    for parts in allowlist.values():
        for part in parts:
            assert part.replace("_", "").isalnum(), part


def test_every_allowlisted_key_renders_both_directions() -> None:
    for key in targets_query.SORT_ALLOWLIST:
        assert rendered(order_by(key, targets_query.SORT_ALLOWLIST, "url_id")).endswith("ASC")
        assert rendered(
            order_by(f"-{key}", targets_query.SORT_ALLOWLIST, "url_id")
        ).endswith("DESC")
