"""DB 접근 계층.

ORM 을 쓰지 않는다. psycopg3 + 명시적 SQL 이다(툴체인 §3).
모든 값은 파라미터 바인딩으로만 전달하고, 식별자를 외부 입력으로 받지 않는다.
"""

from __future__ import annotations

__all__ = ["connect", "contract", "schema_check"]

from lifelaw_web.db import contract, schema_check
from lifelaw_web.db.connection import connect
