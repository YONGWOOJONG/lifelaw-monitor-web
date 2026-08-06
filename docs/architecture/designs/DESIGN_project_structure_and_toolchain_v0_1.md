---
Document-ID: DESIGN-LIFELAW-MONITOR-WEB-TOOLCHAIN
Version: 0.1
Status: PROPOSAL
Authority: ADVISORY
Implementation-Authority: false
Owner: User
Depends-On: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md (v1.2, APPROVED)
---

# 프로젝트 구조와 툴체인 (G-4) — v0.1

> **이 문서는 `PROPOSAL`이며 구현 권위가 아니다.** 다만 여기서 정하는 것은
> 되돌리기 비용이 큰 결정(레이아웃·의존성·마이그레이션 방식)이므로, 코드 작성
> 전에 승인을 받는다.
>
> 상위 권위는 `DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md`다.

---

## 1. 확정 전제

상위 설계 v1.2의 승인 사항에서 그대로 따라오는 것들이다.

| 항목 | 값 | 근거 |
|---|---|---|
| 백엔드 | FastAPI (Python) | A-02, 상위 §2.1 |
| 프론트엔드 | React + TypeScript (Vite) | A-02 |
| 인증 | 서버 측 세션 + 쿠키 | A-04, 상위 §17.4 |
| 배포 형상 | **동일 출처** (리버스 프록시) | 상위 §17.4 강제 조항 1 |
| Web 소유 테이블 | `TW_` 7종 | A-03·A-09, 상위 §7.2 |
| 권한 | 14종 코드 상수 | A-05, 상위 §17.2 |

## 2. 설치 환경 실측 (2026-08-06)

| 도구 | 버전 | 비고 |
|---|---|---|
| Python | 3.12.10 | `requires-python = ">=3.12"` |
| pip | 25.0.1 | |
| Node.js | 26.7.0 | |
| npm | 11.19.0 | |
| PostgreSQL | 18.4 | 서비스 `postgresql-x64-18`, 5432, `UTF8` / `Asia/Seoul` |

참조 저장소는 `requires-python = ">=3.11"`이지만, 이 저장소는 신규이고 설치된
런타임이 3.12이므로 **3.12를 하한으로 잡는다.** 공유 라이브러리를 추출할 때
참조 저장소가 3.11에서 돌아야 하므로, **공유 대상 코드는 3.12 전용 문법을
쓰지 않는다**(§9 참조).

## 3. ORM을 쓰지 않는다

**결정: psycopg3 + 명시적 SQL. ORM(SQLAlchemy 등)을 도입하지 않는다.**

이 프로젝트의 DB 접근은 ORM이 잘 다루지 못하는 것들로 이루어져 있다.

| 요구 | ORM에서의 문제 |
|---|---|
| `GENERATED ALWAYS AS ... STORED` 계산 컬럼 | ORM이 INSERT/UPDATE 목록에 넣으려 해 오류가 난다. 읽기 전용 매핑을 매번 강제해야 함 |
| `POLICY_BARRIER` advisory lock 순서 | 락 획득 순서를 SQL 수준에서 통제해야 함. ORM 세션 flush 시점이 끼어들면 순서가 깨진다 |
| 월별 RANGE 파티션(`TH_CRAWL_TARGET`) | 파티션 프루닝을 위해 조건을 정확히 써야 함 |
| all-or-none 일괄 UPDATE + 버전 재확인 | 단일 문장으로 표현해야 원자성이 보장된다 |
| 컬럼 단위 GRANT (§7) | ORM이 전체 컬럼 UPDATE를 시도하면 권한 오류가 난다 |
| 참조 저장소와 SQL 공유 | 참조 저장소가 raw psycopg를 쓴다. ORM을 끼우면 공유가 불가능 |

부작용으로 **SQL 인젝션 책임이 전적으로 우리에게 온다.** 대응:

- 모든 값은 psycopg 파라미터 바인딩(`%s`)으로만 전달한다. f-string·`%`·`+`로
  SQL을 만들지 않는다
- 테이블명·컬럼명을 외부 입력으로 받지 않는다(상위 §6에서 이미 금지)
- 정렬 컬럼처럼 식별자를 골라야 하는 경우는 **allowlist 매핑**으로 처리한다
- ruff 규칙 `S608`(SQL 문자열 구성)을 **무시하지 않는다**

## 4. 디렉터리 레이아웃

```text
lifelaw-monitor-web/
├── AGENTS.md
├── pyproject.toml
├── .gitignore
├── .env.example                    비밀 키 "이름"만. 값은 넣지 않는다
├── config/
│   └── web.example.json            비밀 아닌 설정만
├── docs/
│   ├── README.md
│   ├── contracts/
│   │   └── db-contract.md          G-1
│   └── architecture/designs/
├── scripts/
│   └── db/
│       ├── migrations/
│       │   └── 0001_create_tw_schema.sql
│       └── apply_migrations.py
├── src/
│   └── lifelaw_web/
│       ├── __init__.py
│       ├── main.py                 앱 팩토리 + 기동 시 fail-closed 검증
│       ├── settings.py             설정·secret 로딩 (§6)
│       ├── db/
│       │   ├── pool.py             커넥션 풀
│       │   ├── schema_check.py     계약 검증 (1단계, 상위 §21)
│       │   └── sql/                이름 있는 SQL 상수 모듈
│       ├── auth/                   세션·CSRF·재인증
│       ├── rbac/
│       │   ├── permissions.py      권한 14종 상수 (단일 출처)
│       │   └── guard.py            default-deny 검사
│       ├── audit/                  append-only 기록
│       ├── dto/                    요청·응답 스키마 (Pydantic)
│       └── api/                    라우터. 화면 단위로 분할
├── tests/
│   ├── unit/
│   ├── integration/                실 PostgreSQL 필요. `-m integration`
│   └── fixtures/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
```

참조 저장소와 같은 `src/` 레이아웃과 `tests/{unit,integration,fixtures}` 계층을
쓴다. 참조 저장소의 `tests/golden`·`tests/semantic_ci`는 수집 파이프라인 전용
개념이므로 가져오지 않는다.

**`rbac/permissions.py`가 권한 문자열의 단일 출처다.** 문자열 리터럴을 라우터에
직접 쓰지 않는다. 상위 §17.2 목록과의 일치를 테스트로 고정한다.

## 5. 의존성

`pyproject.toml`에 **정확한 버전으로 핀**한다(참조 저장소 방식). 아래 버전은
2026-08-06 PyPI 조회로 실재를 확인했다. **추측 핀을 넣지 않는다.**

런타임: `fastapi==0.141.1`, `uvicorn[standard]==0.52.1`,
`psycopg[binary,pool]==3.3.4`, `pydantic==2.13.4`,
`pydantic-settings==2.14.2`, `argon2-cffi==25.1.0`

개발: `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `httpx==0.28.1`,
`ruff==0.16.1`, `mypy==2.3.0`

- **psycopg는 참조 저장소와 동일 핀(3.3.4)을 유지한다.** 어댑터 동작 차이가
  같은 스키마에 대해 다른 결과를 내는 것을 막는다
- 비밀번호 해싱은 **Argon2id**(`argon2-cffi`). bcrypt의 72바이트 절단 문제가 없다
- 가상환경은 표준 `venv`. poetry·uv 같은 추가 도구를 도입하지 않는다
  (참조 저장소와 동일한 최소 툴체인 유지)

프론트엔드는 npm + Vite 템플릿(`react-ts`)을 사용한다. **Node 26은 최신
계열이므로 Vite 호환을 실제 설치 시점에 확인하고, 문제가 있으면 LTS로
내린다**(§10 미결).

## 6. 설정과 secret 계약

참조 저장소 R1의 CUBRID 설정 선례를 그대로 따른다. **비밀이 아닌 값은 JSON,
자격증명은 환경변수.**

`config/web.json` (Git 제외, `web.example.json`만 추적)

```json
{
  "postgres": { "host": "127.0.0.1", "port": 5432, "database": "lifelaw_c" },
  "artifact_root": "C:/lifelaw/artifacts",
  "session": { "idle_minutes": 30, "absolute_hours": 12 }
}
```

환경변수 (`.env.example`에 **이름만** 기록)

```text
LIFELAW_WEB_DB_USER
LIFELAW_WEB_DB_PASSWORD
LIFELAW_WEB_SESSION_SECRET
```

**fail-closed 규칙:**

1. 환경변수가 하나라도 없으면 **기동을 실패시킨다.** 기본값으로 대체하지 않는다
2. **설정 JSON에 `password`·`user`·`secret` 키가 존재하면 거부하고 기동을
   실패시킨다.** 실수로 자격증명을 커밋하는 경로를 구조적으로 막는다
3. 이 검사는 **키 이름 기준**으로 한다. 파일 전체를 문자열로 훑어 금지어를
   찾는 방식은 쓰지 않는다. 설명용 문자열에 "password" 같은 단어가 들어가면
   정상 설정이 거부되는 오탐이 난다. (같은 이유로 `web.example.json`에는
   주석용 필드를 두지 않았다. JSON은 주석을 지원하지 않으므로 설명은 이
   문서에 둔다.)
4. 오류 메시지에 값을 출력하지 않는다. 키 이름만 보고한다(상위 §7)

## 7. DB 계정과 권한 — 컬럼 단위 GRANT

AGENTS.md §7은 DB 소유자 계정 재사용을 금지한다. 3개 롤로 분리한다.

| 롤 | 용도 | 권한 |
|---|---|---|
| `postgres` | 인스턴스 소유자 | 롤·DB 생성에만 사용. 애플리케이션·마이그레이션에서 사용 금지 |
| `lifelaw_web_migrator` | `TW_` DDL 적용 | `TW_` 테이블 생성·변경. 수집기 테이블 DDL 권한 없음 |
| `lifelaw_web_app` | 런타임 | 아래 최소 권한 |

`lifelaw_web_app` 권한 설계:

```text
수집기 소유 테이블
  TC_COMMON_CODE          SELECT
  TN_CNPCLS_CNLNK         SELECT
  TH_CRAWL_TARGET         SELECT
  TN_BATCH_RUN            SELECT
  TN_CRAWL_TARGET         SELECT
                        + UPDATE (target_collect_policy_cd,
                                  collect_target_kind_cd,
                                  target_policy_version)   ← 컬럼 단위
  TN_COLLECT_SITE_POLICY  SELECT, UPDATE (정책 컬럼 한정)

Web 소유 테이블
  TW_USER, TW_ROLE, TW_PERMISSION, TW_ROLE_PERMISSION,
  TW_USER_ROLE, TW_SESSION           SELECT, INSERT, UPDATE, DELETE
  TW_ADMIN_COMMAND                   SELECT, INSERT, UPDATE(status 한정)
  TW_APPROVAL                        SELECT, INSERT
  TW_AUDIT_LOG                       SELECT, INSERT          ← UPDATE/DELETE 미부여
```

**이 설계의 핵심은 PostgreSQL의 컬럼 단위 `GRANT UPDATE`다.** 상위 §7.1의
"실행 상태 컬럼 직접 수정 금지"를 애플리케이션 규율이 아니라 **DB 권한으로
강제**할 수 있다. 코드에 버그가 있어도 `crawl_stat_cd`에 대한 UPDATE는 DB가
거부한다.

같은 원리로 `TW_AUDIT_LOG`에 UPDATE/DELETE를 부여하지 않아 append-only가
애플리케이션 밖에서 보장된다(상위 §15 요구).

## 8. 마이그레이션

**Alembic을 쓰지 않는다.** Alembic은 SQLAlchemy에 묶여 있고 §3에서 ORM을
배제했다.

방식: **번호순 SQL 파일 + 적용 원장 테이블.** 참조 저장소의
`scripts/db/create_c_schema_v2_19.sql` 관행과 결이 같다.

```text
scripts/db/migrations/0001_create_tw_schema.sql
                      0002_....sql
```

- 적용 원장 `TW_SCHEMA_MIGRATION(version, applied_at, checksum)`
- **적용된 파일은 수정하지 않는다.** 이미 적용된 마이그레이션의 checksum이
  달라지면 적용을 거부하고 중단한다
- **마이그레이션 범위는 `TW_` 테이블뿐이다.** 수집기 소유 테이블의 DDL을 이
  저장소의 마이그레이션으로 변경하지 않는다. 필요해지면 중단하고 보고한다
- 롤백 스크립트를 자동 생성하지 않는다. 되돌리기는 명시적 새 마이그레이션이다

## 9. 참조 저장소와의 코드 공유

상위 §2.1은 정책 변경 로직을 공유 라이브러리로 추출할 수 있어야 한다고 본다.
현재는 추출하지 않고, 추출 가능한 상태만 유지한다.

- 공유 후보 코드는 **Python 3.11 호환 문법**으로 쓴다(참조 저장소 하한)
- 공유 후보는 psycopg 연결 객체를 인자로 받고, 설정·로깅·프레임워크에
  의존하지 않는다
- 실제 추출은 별도 승인 사항이다. 그때까지 Web은 §10 절차를 **재현**한다

## 10. 미결 사항

| # | 항목 | 결정 필요 시점 |
|---|---|---|
| T-1 | Node 26에서 Vite/React 템플릿 정상 동작 여부. 문제 시 LTS로 하향 | 프론트 스캐폴딩 시 |
| T-2 | 개발용 데이터베이스 이름(`lifelaw_c` 제안)과 수집기 스키마 적용 주체 | DB 생성 시 |
| T-3 | 리버스 프록시 실체 (개발은 Vite proxy, 운영은 미정) | 배포 설계 시 |
| T-4 | 로깅 형식 — 참조 저장소 D-22 로깅 baseline과 정합 필요 | 1단계 구현 시 |
| T-5 | CI 도입 여부 (원격 저장소 보류 상태이므로 현재 불가) | 원격 승인 후 |

## 11. SELF-REFINE

| 공격 질문 | 판정 | 대응 |
|---|---|---|
| ORM 배제가 SQL 인젝션 위험을 키우는가 | **위험 인지** | 키운다. §3에 파라미터 바인딩 강제·식별자 allowlist·`S608` 미무시를 대응으로 고정 |
| 의존성 핀이 실재하는 버전인가 | **수정함** | 초안은 기억에 의존한 추측 핀이었고 11개 중 7개가 존재하지 않는 버전이었다. PyPI 실조회로 교체하고 "추측 핀 금지"를 규칙으로 명시 |
| 컬럼 단위 GRANT가 실제로 상태 컬럼 쓰기를 막는가 | 통과 | PostgreSQL은 컬럼 단위 UPDATE 권한을 지원한다. 다만 **부여 스크립트가 실제로 적용됐는지**를 기동 검증에 포함해야 한다 → §7을 1단계 검증 항목에 추가 |
| Python 3.12 하한이 공유 라이브러리 경로를 깨뜨리는가 | **수정함** | 참조 저장소 하한이 3.11이다. §9에 "공유 후보는 3.11 호환 문법" 규칙 추가 |
| `.gitignore`가 자격증명 유입을 실제로 막는가 | 통과 | `config/*.json` 전체 제외 + `*.example.json`만 예외. `.env` 제외. 다만 §6 규칙 2(설정 JSON에 비밀 키 존재 시 기동 거부)가 2차 방어선 |
| 마이그레이션이 수집기 스키마를 건드릴 여지가 있는가 | 통과 | §8에서 `TW_` 한정을 명시하고 필요 시 중단 조건으로 규정 |
| Alembic 배제가 나중에 후회할 결정인가 | 잔여 위험 | ORM을 도입하지 않는 한 유효하다. ORM 재검토 시 함께 재검토한다 |
