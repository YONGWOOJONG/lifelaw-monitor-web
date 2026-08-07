"""서버 측 페이징과 정렬.

권위: DESIGN_admin_screen_inventory_v0_1.md S-04
      DESIGN_project_structure_and_toolchain_v0_1.md §3

규칙:
  - **정렬 컬럼을 외부 입력으로 받지 않는다.** 클라이언트는 정렬 *키*를 보내고,
    서버가 allowlist 로 실제 컬럼을 고른다.
  - SQL 은 f-string 으로 조립하지 않는다. 식별자는 `psycopg.sql.Identifier`,
    고정 조각은 `psycopg.sql.SQL` 로 합성한다. 툴체인 §3 이 ruff `S608` 을
    무시하지 말라고 한 이유가 이것이며, 억지로 억제하는 대신 애초에 문자열
    보간을 하지 않는 방식으로 만족시킨다.
  - 전체 건수는 목록과 **분리한다**. 대용량 테이블에서 매 요청 COUNT 를 도는
    것을 피한다(S-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from psycopg import sql

DEFAULT_LIMIT: Final = 50
MAX_LIMIT: Final = 200  # 설계 §20.2 일괄 변경 상한과 같은 값
MAX_OFFSET: Final = 100_000

# 정렬 키 → 스키마 한정 컬럼. 값은 Identifier 로만 SQL 에 들어간다.
SortAllowlist = dict[str, tuple[str, ...]]


class SortError(ValueError):
    """허용되지 않은 정렬 키."""


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def normalised(self) -> PageParams:
        limit = max(1, min(self.limit, MAX_LIMIT))
        offset = max(0, min(self.offset, MAX_OFFSET))
        return PageParams(limit=limit, offset=offset)


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    limit: int
    offset: int
    has_more: bool


def build_page[T](rows: list[T], params: PageParams) -> Page[T]:
    """limit+1 로 조회한 결과를 잘라 has_more 를 판정한다.

    COUNT 없이 "다음 페이지 있음"을 알 수 있다.
    """
    has_more = len(rows) > params.limit
    return Page(
        items=rows[: params.limit],
        limit=params.limit,
        offset=params.offset,
        has_more=has_more,
    )


def order_by(sort_key: str | None, allowlist: SortAllowlist, default: str) -> sql.Composed:
    """정렬 키를 ORDER BY 조각으로 바꾼다.

    사용자 문자열은 **키 조회에만** 쓰이고 SQL 에 들어가지 않는다.
    `-` 접두사는 내림차순이다.

    빈 값과 공백만 있는 값은 "정렬 미지정"으로 보고 기본 키를 쓴다. `?sort=` 처럼
    비어 있는 쿼리 파라미터가 오류가 되지 않게 하되, 그 외의 모르는 키는 거부한다.
    """
    key = (sort_key or "").strip() or default.strip()
    descending = key.startswith("-")
    if descending:
        key = key[1:]
    column = allowlist.get(key)
    if column is None:
        raise SortError(f"정렬 키가 올바르지 않습니다: {key}")
    direction = sql.SQL("DESC") if descending else sql.SQL("ASC")
    return sql.SQL("{} {}").format(sql.Identifier(*column), direction)


def where_clause(conditions: list[sql.Composable]) -> sql.Composable:
    if not conditions:
        return sql.SQL("")
    return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)


def limit_offset() -> sql.Composable:
    return sql.SQL(" LIMIT %s OFFSET %s")
