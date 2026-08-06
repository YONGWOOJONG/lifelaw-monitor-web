"""DB 연결.

권위: docs/contracts/db-contract.md §2.7 (시간과 일자)
      DESIGN_project_structure_and_toolchain_v0_1.md §3

세션 타임존을 명시 고정한다. 서버 기본값에 의존하면 같은 쿼리가 환경에 따라
다른 결과를 낸다. `batch_ymd` 는 서울 업무일자 문자열이므로 일자 경계 계산은
문자열 비교로 처리하고, 타임스탬프 변환에 세션 TZ 가 끼어들지 않게 한다.

타임존은 `SET TIME ZONE` 문이 아니라 **연결 옵션**으로 넘긴다. `SET` 은 파라미터
바인딩을 받지 않으므로 SQL 문으로 처리하면 문자열 조립이 필요해지고, 그것은
툴체인 §3 의 "값은 파라미터 바인딩으로만" 규칙과 어긋난다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from lifelaw_web.settings import SESSION_TIME_ZONE, Settings

# 연결 옵션 문자열. 상수이며 외부 입력이 섞이지 않는다.
_SESSION_OPTIONS = f"-c timezone={SESSION_TIME_ZONE}"


@contextmanager
def connect(settings: Settings, *, autocommit: bool = False) -> Iterator[psycopg.Connection[Any]]:
    """설정으로 연결을 열고 세션 타임존을 고정한다."""
    with psycopg.connect(
        **settings.conninfo_kwargs,
        options=_SESSION_OPTIONS,
        autocommit=autocommit,
    ) as conn:
        yield conn


def session_time_zone(conn: psycopg.Connection[Any]) -> str:
    """실제 적용된 세션 타임존. 검증과 진단에 쓴다."""
    with conn.cursor() as cur:
        cur.execute("SHOW TimeZone")
        row = cur.fetchone()
    return str(row[0]) if row else ""
