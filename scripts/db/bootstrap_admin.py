"""최초 ADMIN 계정 부트스트랩.

권위:
  DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7.2 §17 §19
  docs/runbooks/dev-database-setup.md RB-1

성격:
  create-only. 이미 계정이 존재하면 아무것도 하지 않고 실패한다.
  기존 계정의 비밀번호를 재설정하는 용도가 아니다.

비밀정보:
  비밀번호를 이 파일에 넣지 않는다. 환경변수로만 받는다.
      LIFELAW_WEB_BOOTSTRAP_PASSWORD   생성할 계정의 비밀번호
      LIFELAW_WEB_DB_USER              DB 접속 롤 (lifelaw_web_app)
      LIFELAW_WEB_DB_PASSWORD          DB 접속 비밀번호
  하나라도 없으면 기동을 실패시킨다(fail-closed). 기본값으로 대체하지 않는다.

권한:
  런타임 롤(lifelaw_web_app)의 권한만으로 동작한다. TW_USER / TW_USER_ROLE
  INSERT 와 TW_AUDIT_LOG INSERT 로 충분하므로 소유자 계정을 쓰지 않는다.

사용:
    LIFELAW_WEB_BOOTSTRAP_PASSWORD=... .venv/Scripts/python.exe \
        scripts/db/bootstrap_admin.py --login-id admin --user-nm "시스템관리자"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from argon2 import PasswordHasher
from argon2.profiles import RFC_9106_LOW_MEMORY

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "web.json"
FORBIDDEN_CONFIG_KEYS = {"user", "password", "secret"}
BOOTSTRAP_ROLE = "ADMIN"
ACTOR = "bootstrap"


class BootstrapError(RuntimeError):
    """중단 조건. 메시지에 값을 담지 않고 키 이름만 담는다."""


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BootstrapError(f"환경변수 {name} 가 없습니다. 기본값으로 대체하지 않습니다.")
    return value


def _walk_keys(obj: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.append(prefix + key)
            found.extend(_walk_keys(value, prefix + key + "."))
    return found


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise BootstrapError(f"설정 파일이 없습니다: {CONFIG_PATH.name}")
    config: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    # fail-closed: 설정 파일에 자격증명 키가 있으면 거부한다.
    # 키 이름 기준으로만 판정한다. 파일 전체를 문자열로 훑으면 설명 문구에
    # "password" 가 들어간 정상 설정도 거부되는 오탐이 난다.
    leaked = [k for k in _walk_keys(config) if k.split(".")[-1].lower() in FORBIDDEN_CONFIG_KEYS]
    if leaked:
        raise BootstrapError(f"설정 파일에 자격증명 키가 있습니다: {', '.join(sorted(leaked))}")

    if "postgres" not in config:
        raise BootstrapError("설정 파일에 postgres 항목이 없습니다.")
    return config


def hash_password(plaintext: str) -> str:
    # RFC 9106 low-memory 프로파일. Argon2id 이며 bcrypt 의 72바이트 절단 문제가 없다.
    hasher = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)
    encoded = hasher.hash(plaintext)
    # DDL 제약 ck_tw_user_pwd_argon2 와 동일한 조건을 코드에서도 확인한다.
    if not encoded.startswith("$argon2id$"):
        raise BootstrapError("해시 형식이 Argon2id 가 아닙니다.")
    # 자기 검증. 저장한 해시로 원문이 실제 검증되는지 확인한다.
    hasher.verify(encoded, plaintext)
    return encoded


def bootstrap(conn: psycopg.Connection, login_id: str, user_nm: str, password: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tw_user")
        row = cur.fetchone()
        existing = int(row[0]) if row else 0
        if existing:
            raise BootstrapError(
                f"이미 계정이 {existing}건 존재합니다. 이 스크립트는 create-only 입니다."
            )

        cur.execute("SELECT 1 FROM tw_role WHERE role_cd = %s", (BOOTSTRAP_ROLE,))
        if cur.fetchone() is None:
            raise BootstrapError(
                f"역할 {BOOTSTRAP_ROLE} 이 없습니다. 마이그레이션 0001 을 먼저 적용하세요."
            )

        cur.execute(
            """
            INSERT INTO tw_user (login_id, user_nm, password_hash, use_yn, reger, moder)
            VALUES (%s, %s, %s, 'Y', %s, %s)
            RETURNING user_id
            """,
            (login_id, user_nm, hash_password(password), ACTOR, ACTOR),
        )
        row = cur.fetchone()
        if row is None:
            raise BootstrapError("계정 INSERT 가 user_id 를 반환하지 않았습니다.")
        user_id = int(row[0])

        cur.execute(
            "INSERT INTO tw_user_role (user_id, role_cd, reger) VALUES (%s, %s, %s)",
            (user_id, BOOTSTRAP_ROLE, ACTOR),
        )

        # 감사 로그. 비밀번호와 해시는 절대 남기지 않는다.
        cur.execute(
            """
            INSERT INTO tw_audit_log
                (actor, actor_role_cd, action, target_type, target_id,
                 before_value, after_value, reason, result_cd)
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, 'SUCCESS')
            """,
            (
                ACTOR,
                BOOTSTRAP_ROLE,
                "BOOTSTRAP_ADMIN",
                "TW_USER",
                str(user_id),
                json.dumps(
                    {"login_id": login_id, "user_nm": user_nm, "roles": [BOOTSTRAP_ROLE]},
                    ensure_ascii=False,
                ),
                "최초 관리자 계정 부트스트랩",
            ),
        )
    return user_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="최초 ADMIN 계정을 생성한다 (create-only)")
    parser.add_argument("--login-id", required=True)
    parser.add_argument("--user-nm", required=True)
    args = parser.parse_args(argv)

    try:
        config = load_config()
        password = require_env("LIFELAW_WEB_BOOTSTRAP_PASSWORD")
        db_user = require_env("LIFELAW_WEB_DB_USER")
        db_password = require_env("LIFELAW_WEB_DB_PASSWORD")
        pg = config["postgres"]

        with psycopg.connect(
            host=pg["host"],
            port=pg["port"],
            dbname=pg["database"],
            user=db_user,
            password=db_password,
            autocommit=False,
        ) as conn:
            # 세션 타임존을 고정한다. 서버 기본값에 의존하지 않는다(D-26).
            with conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'Asia/Seoul'")
            user_id = bootstrap(conn, args.login_id, args.user_nm, password)
            conn.commit()
    except BootstrapError as exc:
        print(f"중단: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        # DSN·자격증명이 새지 않도록 예외 클래스와 SQLSTATE 만 보고한다.
        print(f"DB 오류: {type(exc).__name__} sqlstate={exc.sqlstate}", file=sys.stderr)
        return 3

    print(f"생성 완료: user_id={user_id} login_id={args.login_id} role={BOOTSTRAP_ROLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
