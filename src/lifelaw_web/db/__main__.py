"""DB 계약 검증 CLI.

    .venv/Scripts/python.exe -m lifelaw_web.db

종료 코드:
    0  전부 통과
    1  계약 불일치 (기동을 막아야 하는 상태)
    2  설정·환경변수 오류

화면 S-21(계약·스키마 상태)이 보여줄 내용과 같은 데이터를 출력한다.
"""

from __future__ import annotations

import sys

import psycopg

from lifelaw_web.db import contract
from lifelaw_web.db.connection import connect, session_time_zone
from lifelaw_web.db.schema_check import run_all
from lifelaw_web.settings import SettingsError, load_settings


def main(argv: list[str] | None = None) -> int:
    del argv
    # Windows 콘솔은 cp949 일 수 있다. 인코딩할 수 없는 문자로 출력이 죽는 것을
    # 막는다. 진단 도구가 인코딩 때문에 실패하면 진단 자체를 못 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2

    print("계약 버전 핀")
    print(f"  C1 {contract.C1_DOC_VERSION} / G1 {contract.G1_DOC_VERSION}")
    print(f"  DDL {contract.DDL_FILENAME}")
    print(f"  기대 마이그레이션 {contract.EXPECTED_MIGRATION_VERSION}")
    print(f"  대상 {settings.config.postgres.database} @ {settings.config.postgres.host}")
    print()

    try:
        with connect(settings) as conn:
            tz = session_time_zone(conn)
            results = run_all(conn, settings.secrets.db_user)
    except psycopg.Error as exc:
        # DSN·자격증명이 새지 않도록 예외 클래스와 SQLSTATE 만 보고한다.
        print(
            f"검증 실행 실패: {type(exc).__name__} sqlstate={exc.sqlstate}",
            file=sys.stderr,
        )
        return 1

    print(f"세션 타임존: {tz}")
    print()

    failed = 0
    for r in results:
        if r.informational:
            mark = "INFO"
        elif r.ok:
            mark = "PASS"
        else:
            mark = "FAIL"
            failed += 1
        print(f"{mark:5} {r.check_id:6} {r.title} | {r.detail}")

    print()
    if failed:
        print(f"실패 {failed}건. 이 상태에서는 애플리케이션을 기동하지 않는다.")
        return 1
    print(f"전부 통과 ({len(results)}건).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
