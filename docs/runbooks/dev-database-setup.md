---
Document-ID: RUNBOOK-LIFELAW-MONITOR-WEB-DEV-DB
Version: 0.1
Status: PROPOSAL
Authority: ADVISORY
Implementation-Authority: false
Owner: User
Depends-On: db-contract.md, DESIGN_project_structure_and_toolchain_v0_1.md
---

# 개발 데이터베이스 구성 러너북 — v0.1

2026-08-06 실제 실행 결과를 기록한 재현 절차다. **실행하지 않은 단계는 적지
않았고, 실행 결과가 예상과 달랐던 것은 §7에 남겼다.**

---

## 1. 전제

| 항목 | 값 |
|---|---|
| PostgreSQL | 18.4, 서비스 `postgresql-x64-18`, 127.0.0.1:5432 |
| 데이터베이스 | `lifelaw_c` (UTF8 / `Korean_Korea.949`) |
| psql | `C:\Program Files\PostgreSQL\18\bin\psql.exe` |
| 참조 DDL | `c:\project\lifelaw-monitor\scripts\db\create_c_schema_v2_19.sql` |
| DDL SHA-256 | `3b8fbfa14fa396b4e75996558aad2e18c6fd2c0007501d3bef37f49bfc7db9fa` |

**자격증명은 이 문서에 적지 않는다.** 로컬 `.env`(Git 제외)에 있다.

---

## 2. 실행 순서

### 2.1 DDL 무결성 확인 (중단 조건)

```bash
sha256sum /c/project/lifelaw-monitor/scripts/db/create_c_schema_v2_19.sql
# 계약 §1 의 핀과 불일치하면 즉시 중단한다.
```

**DDL 사본을 이 저장소에 만들지 않는다.** 원본 경로에서 실행한다.

### 2.2 데이터베이스 생성

```sql
CREATE DATABASE lifelaw_c ENCODING 'UTF8' TEMPLATE template0;
```

### 2.3 롤 생성

```sql
CREATE ROLE lifelaw_collector_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE lifelaw_web_migrator LOGIN PASSWORD '<secret>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE lifelaw_web_app LOGIN PASSWORD '<secret>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO lifelaw_collector_owner, lifelaw_web_migrator, lifelaw_web_app;
GRANT CREATE ON SCHEMA public TO lifelaw_web_migrator;
GRANT CONNECT ON DATABASE lifelaw_c TO lifelaw_web_migrator, lifelaw_web_app;
```

### 2.4 C 스키마 적용 — 대상이 비어 있을 때만

```bash
# 사전 확인: public 스키마 테이블 수가 0 이어야 한다
psql -U postgres -d lifelaw_c -tAc \
  "select count(*) from pg_tables where schemaname='public';"

psql -U lifelaw_web_migrator -d lifelaw_c -v ON_ERROR_STOP=1 \
  -f /c/project/lifelaw-monitor/scripts/db/create_c_schema_v2_19.sql
```

이 스크립트는 **non-idempotent**다. 재실행하면 실패한다. 실패했으면 DB를
drop 하고 2.2부터 다시 한다(개발 DB이므로 허용).

### 2.5 소유권 이전 — 반드시 수행

```sql
ALTER TABLE tc_common_code         OWNER TO lifelaw_collector_owner;
ALTER TABLE tn_collect_site_policy OWNER TO lifelaw_collector_owner;
ALTER TABLE tn_cnpcls_cnlnk        OWNER TO lifelaw_collector_owner;
ALTER TABLE tn_crawl_target        OWNER TO lifelaw_collector_owner;
ALTER TABLE th_crawl_target        OWNER TO lifelaw_collector_owner;
ALTER TABLE tn_batch_run           OWNER TO lifelaw_collector_owner;
```

> **이 단계를 빠뜨리면 §2.7의 컬럼 단위 권한 통제가 전부 무효가 된다.**
> 테이블 소유자는 자신의 테이블에 대한 GRANT 제약을 우회한다. 시퀀스 소유권도
> `ALTER TABLE`로 함께 이전된다.

### 2.6 TH 월 파티션

```bash
psql -U postgres -d lifelaw_c -v ON_ERROR_STOP=1 \
  -f scripts/db/partitions/th_partitions_2026_06_08.sql
```

현재 업무월 + 직전 2개 달. 월이 바뀌면 새 파티션 스크립트를 추가한다.
파티션이 없는 `batch_ymd`는 INSERT가 거부되며, 이는 정상 동작이다.

### 2.7 TW_ 스키마와 권한

```bash
psql -U lifelaw_web_migrator -d lifelaw_c -v ON_ERROR_STOP=1 \
  -f scripts/db/migrations/0001_create_tw_schema.sql

# 적용 원장 기록 (checksum 은 파일의 SHA-256)
psql -U lifelaw_web_migrator -d lifelaw_c -v sum="$(sha256sum scripts/db/migrations/0001_create_tw_schema.sql | cut -d' ' -f1)" <<'SQL'
INSERT INTO tw_schema_migration (version, filename, checksum)
VALUES ('0001', '0001_create_tw_schema.sql', :'sum');
SQL

# GRANT 는 소유자 권한이 필요하다
psql -U postgres -d lifelaw_c -v ON_ERROR_STOP=1 -f scripts/db/grants/0001_grants.sql
```

`psql -c` 에서는 `:'var'` 보간이 동작하지 않는다. 반드시 stdin 또는 `-f`를 쓴다.

### 2.8 검증

```bash
psql -U postgres -d lifelaw_c -f scripts/db/verify/contract_checks.sql
```

---

## 3. 실행 결과 (2026-08-06 실측)

| 검증 | 기대 | 실측 |
|---|---|---|
| V-01 테이블 6개 | 6 | **6** |
| V-02 allowlist 컬럼 | 9 | **9** |
| V-03 TN 계산 컬럼 STORED GENERATED | 2행 모두 `s` | **`s`, `s`** |
| V-04 `run` 항 유무 | effective=f, execution=t | **f / t** |
| V-05 공통 코드 | 34건, 전부 `use_yn='Y'` | **34 / 34** |
| V-06 TH 파티션 테이블 | `p` | **`p`** |
| V-07 파티션 목록 | 3개 | **2026_06 / 07 / 08** |
| V-08 CHECK 제약 (conrelid 지정) | 7행 | **7** |
| V-09 `TW_AUDIT_LOG` UPDATE/DELETE | 0행 | **0행** |
| V-10 `TN_CRAWL_TARGET` UPDATE 컬럼 | allowlist 4개 | **4개 일치** |
| V-10b 금지 컬럼 UPDATE 권한 | 0행 | **0행** |
| V-11 마이그레이션 원장 | `0001` | **0001, checksum `9073bceb…`** |
| 보강 수집기 테이블 소유자 | Web 롤 아님 | **전부 `lifelaw_collector_owner`** |
| 보강 RBAC seed | role=6 perm=14 role_perm=35 | **6 / 14 / 35** |
| 보강 ADMIN의 `command:approve` | 0행 (4-eyes) | **0행** |

### 3.1 권한 프로브 46개 — 전부 PASS

거부 33건: 실행 상태 5종, `run_*` 3종, 해시·진단·파일·방법 컬럼, `batch_ymd`,
계산 컬럼 직접 쓰기, `TN_CRAWL_TARGET` INSERT/DELETE, `TH_CRAWL_TARGET`
INSERT/UPDATE, `TN_BATCH_RUN` INSERT/UPDATE, `TC_COMMON_CODE` INSERT/UPDATE/
DELETE(`use_yn` 토글 포함), `TN_CNPCLS_CNLNK` UPDATE, `TW_AUDIT_LOG`
UPDATE/DELETE, `TW_APPROVAL` UPDATE/DELETE, `TW_ADMIN_COMMAND` DELETE 및
`payload`/`requested_by` UPDATE, `TW_SESSION` `user_id`/`absolute_expires_at`
UPDATE, `TW_SCHEMA_MIGRATION` INSERT, `CREATE TABLE`

허용 13건: 6개 테이블 SELECT, 대상 직접 정책 UPDATE, 사이트 정책 UPDATE,
`TW_AUDIT_LOG` INSERT, `TW_SESSION.last_seen_at` UPDATE,
`TW_ADMIN_COMMAND.status` UPDATE, `TW_SCHEMA_MIGRATION` SELECT, `TW_USER` SELECT

프로브가 남긴 감사 행 2건은 삭제해 `tw_audit_log`를 0행으로 되돌렸다.

### 3.2 파티션 라우팅 실검증

`batch_ymd='20260715'` → `th_crawl_target_2026_07`로 라우팅 확인(INSERT 후
ROLLBACK). `batch_ymd='20260515'`는 파티션 부재로 거부됨 — 기대 동작.

---

## 4. 현재 데이터 상태

| 테이블 | 행수 | 출처 |
|---|---|---|
| `TC_COMMON_CODE` | 34 | DDL seed |
| `TW_ROLE` / `TW_PERMISSION` / `TW_ROLE_PERMISSION` | 6 / 14 / 35 | 마이그레이션 0001 seed |
| `TW_USER` / `TW_USER_ROLE` | 1 / 1 | 부트스트랩 (§8) |
| `TW_AUDIT_LOG` | 1 | 부트스트랩 감사 기록 |
| `TN_COLLECT_SITE_POLICY` | 8 | **개발 시드 (§9)** |
| `TN_CNPCLS_CNLNK` / `TN_CRAWL_TARGET` | 120 / 120 | **개발 시드 (§9)** |
| `TH_CRAWL_TARGET` | 594 | **개발 시드 (§9)** |
| `TN_BATCH_RUN` | 13 | **개발 시드 (§9)** |
| `TW_SESSION` / `TW_ADMIN_COMMAND` / `TW_APPROVAL` | 0 | — |

**수집기는 아직 실행되지 않았다.** 위 수집 데이터는 §9의 개발 전용 시드이며
상태 조합이 **가정**이다. 실제 수집 결과를 확보하면 시드를 폐기하고 그것으로
대체한다.

---

## 5. 재구성 (개발 DB 초기화)

```sql
-- 접속을 끊고
DROP DATABASE lifelaw_c;
DROP ROLE lifelaw_web_app;
DROP ROLE lifelaw_web_migrator;
DROP ROLE lifelaw_collector_owner;
```

그 후 §2부터 다시 실행한다. **운영 DB에서는 이 절차를 쓰지 않는다.**

---

## 6. 미결 사항

| # | 항목 |
|---|---|
| RB-1 | ~~최초 `ADMIN` 계정 생성 방법~~ **해소** — CLI 스크립트 방식 확정. §8 참조 |
| RB-2 | `command:resync` 를 어느 역할에 부여할지. 설계에 대응 화면이 없어 현재 미부여 |
| RB-3 | `artifact:read` 는 A-08 미승인이라 미부여. 승인 시 부여 대상 결정 |
| RB-4 | 세션 유휴 30분 / 절대 12시간은 제안값. 운영 확정 필요 |
| RB-5 | 월 파티션 자동 생성 방식(수동 스크립트 유지 vs 배치) |
| RB-6 | ~~조회 화면 개발용 데이터 확보~~ **해소** — 개발 전용 시드 도구 도입. §9 참조. 단 상태 조합은 가정이며 실제 수집 결과로 대체해야 한다 |
| RB-7 | 첫 로그인 시 비밀번호 변경 강제 기능 (현재 스키마에 없음. 마이그레이션 0002 대상) |

---

## 7. 이 작업에서 실제로 발생한 문제와 조치

투명성을 위해 남긴다. 모두 실행 중 발견해 조치했다.

| # | 문제 | 조치 |
|---|---|---|
| 1 | C 스키마를 `lifelaw_web_migrator`로 적용해 **Web 롤이 수집기 테이블 소유자**가 됐다. 소유자는 컬럼 단위 GRANT를 우회하므로 권한 모델이 무효가 될 상태였다 | `lifelaw_collector_owner`(NOLOGIN) 신설 후 6개 테이블 + 시퀀스 소유권 이전. 툴체인 §7과 러너북 §2.5에 필수 단계로 명시 |
| 2 | 권한 프로브 33건이 전부 거짓 FAIL로 보고됐다. 판정을 오류 **메시지 문자열**로 했고 PostgreSQL 한국어 메시지가 `"접근 권한 없음"`이라 grep 패턴과 어긋났다 | 종료 코드 판정으로 교체. 계약 §3.1에 "메시지 문자열로 판정하지 않는다"를 함정으로 기록 |
| 3 | V-08이 기대 7에 실측 10. **파티션이 부모의 CHECK 제약을 복제**한다 | 쿼리에 `conrelid`를 함께 지정. 계약 §3.1에 기록 |
| 4 | 공통 코드가 계약 문서의 33건이 아니라 **34건**이었다 | 계약 §2.6·V-05를 34로 정정 |
| 5 | 자격증명 임시 파일을 저장소 안에 만들어 `.gitignore`에 걸리지 않았다 | 즉시 저장소 밖 스크래치패드로 이동. 저장소에 미추적 비밀 파일 0건 확인 |
| 6 | `psql -c` 에서 `:'var'` 보간이 동작하지 않아 원장 INSERT가 실패했다 | stdin 방식으로 교체. §2.7에 명시 |

---

## 8. Python 환경과 최초 ADMIN 계정 (RB-1 해소)

### 8.1 가상환경

```bash
python -m venv .venv                       # Python 3.12.10
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

`.venv/`는 `.gitignore` 대상이다. 설치 결과가 `pyproject.toml`의 핀과 일치하는지
확인한다(2026-08-06 실측: 11개 전부 일치).

### 8.2 로컬 설정 파일

`config/web.json`을 `config/web.example.json`에서 복사해 만든다. Git 제외 대상이며
**`user`/`password`/`secret` 키를 넣지 않는다.** 자격증명은 `.env`로 주입한다.

### 8.3 최초 ADMIN 계정 생성

```bash
set -a; . ./.env; set +a
export LIFELAW_WEB_BOOTSTRAP_PASSWORD='<비밀번호>'
.venv/Scripts/python.exe scripts/db/bootstrap_admin.py \
    --login-id admin --user-nm "시스템관리자"
```

설계상 성질:

- **create-only.** `TW_USER`에 행이 하나라도 있으면 거부한다. 기존 계정의
  비밀번호 재설정 도구가 아니다
- 비밀번호를 인자나 파일로 받지 않는다. **환경변수만** 사용하고, 누락 시
  기동을 실패시킨다
- 해시는 **Argon2id / RFC 9106 low-memory**(`m=65536, t=3, p=4`). 저장 직후
  같은 원문으로 검증까지 수행한다
- 런타임 롤(`lifelaw_web_app`) 권한만으로 동작한다. 소유자 계정을 쓰지 않는다
- 세션 타임존을 `Asia/Seoul`로 고정해 서버 기본값에 의존하지 않는다(D-26)
- 감사 로그에 `BOOTSTRAP_ADMIN` 1건을 남기며, **비밀번호와 해시는 기록하지 않는다**

### 8.4 실측 결과 (2026-08-06)

| 검증 | 결과 |
|---|---|
| 계정 생성 | `user_id=1`, `login_id=admin`, `use_yn=Y`, `reger=bootstrap` |
| 역할 | `ADMIN` |
| 해시 | `$argon2id$v=19$m=65536,t=3,p=4…` 길이 97 |
| 유효 권한 | `target:read`, `target:history:read`, `batch:read`, `policy:read`, `user:manage` |
| **비누적 확인** | `command:approve` **미포함** — 4-eyes 유지 |
| 비밀번호 왕복 | 올바른 값 검증 성공 / 틀린 값 정상 거부 |
| 감사 로그 | 1건. 비밀번호 원문·해시 문자열 포함 0건 |
| create-only | 재실행 시 exit=2로 거부, 계정 1건 유지 |
| 정적 검사 | `ruff` 통과, `mypy --strict` 통과 |

### 8.5 이 계정의 위험

이 계정에 설정한 개발용 비밀번호는 **약하고 로컬 개발 DB 전용**이다. 값은 이
문서에 적지 않는다(AGENTS.md §7). 계정은 `user:manage`를 가지며 §18 최고 위험
작업의 재인증 근거가 되므로, 공유 환경·운영에서는

1. 비밀번호를 재발급하고
2. `.env`를 배포 secret으로 대체하고
3. 이 부트스트랩 계정을 사용 중지(`use_yn='N'`)하고 개인 계정으로 전환한다

비밀번호 변경 강제(첫 로그인 시 재설정) 기능은 현재 스키마에 없다. 필요하면
마이그레이션 0002 대상이다.

---

## 9. 개발 전용 수집 데이터 시드 (RB-6 해소)

### 9.1 성격과 한계

> **이 데이터의 상태 조합은 가정이다.** 수집기가 실제로 만들어내는 조합의 권위
> 있는 정의는 참조 저장소 R2/R3/R5/R6/R7 이며, 시드는 그것을 재현하지 않는다.
> DDL 제약을 만족하는 "그럴듯한" 조합으로 **화면 개발과 성능 검증**을 하려는
> 것이다. 수집기 동작의 근거로 인용하지 않고, 실제 수집 결과를 확보하면 폐기한다.

- **개발 전용.** 운영에 배포하지 않는다
- 수집기 소유 테이블에 쓰므로 **Web 런타임 롤로는 동작하지 않는다.** 설계대로다
  (계약 §2.9). DB 소유자 권한으로 실행한다
- **결정적**이다. 난수를 쓰지 않으므로 재실행 결과가 같고 테스트가 흔들리지 않는다
- URL 은 RFC 2606/6761 예약 도메인(`example.test`, `example.invalid`)만 쓴다.
  실제 사이트를 수집 대상으로 만들지 않는다

### 9.2 실행

```bash
LIFELAW_WEB_SEED_CONFIRM=yes \
LIFELAW_WEB_SEED_DB_USER=postgres \
LIFELAW_WEB_SEED_DB_PASSWORD='<비밀번호>' \
.venv/Scripts/python.exe scripts/db/seed/dev_seed.py [--reset]
```

가드:

- `LIFELAW_WEB_SEED_CONFIRM=yes` 없으면 거부한다
- `tn_crawl_target` 에 행이 있으면 `--reset` 없이는 거부한다

### 9.3 적재 결과 (2026-08-06 실측)

| 테이블 | 행수 |
|---|---|
| `TN_COLLECT_SITE_POLICY` | 8 (수집 5 / 제외 3) |
| `TN_CNPCLS_CNLNK` | 120 |
| `TN_CRAWL_TARGET` | 120 |
| `TH_CRAWL_TARGET` | 594 (2026-06 399 / 07 182 / 08 13) |
| `TN_BATCH_RUN` | 13 |

포함한 상태 다양성:

| 축 | 값 |
|---|---|
| `crawl_stat_cd` | 1010 대기 16 / 1020 성공 72 / 1090 실패 32 |
| `change_yn_cd` | 5000 64 / **5001 기준선 16** / 5010 8 / 5020 16 / 5030 8 / 5040 8 |
| 진단 | 8010 8건 / 8020 8건 (CHECK 5조건 충족) |
| 제외 유형 | 사이트 상속 / 대상 직접(종류코드 동반) / 실행 중 redirect |
| **`effective` ≠ `execution`** | **6건** — 두 계산 컬럼 구분을 화면에서 검증할 수 있다 |
| 배치 모드·상태 | fresh / resume / rerun, 6010·6020·6030·6040·6080·6090 |

`url_id`(1~120)와 `con_link_seq`(1001~1120)를 **다르게** 뒀다. 두 식별자를
혼용하는 버그를 데이터가 잡아준다.

### 9.4 품질 게이트

`tests/integration/test_dev_seed_data.py` 가 불변식을 검사한다. 상태 조합은
가정이지만 아래는 DDL 제약과 업무 의미에서 나오는 것이므로 어길 수 없다.

- 이력에 **미래 업무일자가 없음** (초안에서 실제로 위반했다. §10 참조)
- 계산 컬럼이 OR 규칙과 일치
- `effective ≠ execution` 행이 최소 1건 존재
- 진단 행이 5조건 전부 충족
- 종류 코드와 링크 분류 일치
- `5010`/`5030`(변경 없음)의 해시가 기준선과 동일
- 실행 중·대기 배치에 종료 시각 없음
- 페이징·일괄 상한 검증에 충분한 건수(대상 100+, 이력 300+)
- 예약 도메인만 사용

### 9.5 재구성

```bash
... --reset   # 시드 데이터만 지우고 다시 넣는다 (TW_ 는 건드리지 않는다)
```

`--reset` 은 `TH_`→`TN_CRAWL_TARGET`→`TN_CNPCLS_CNLNK`→`TN_BATCH_RUN`→
`TN_COLLECT_SITE_POLICY` 순으로 지운다(FK 역순). `TW_` 테이블과 관리자 계정은
건드리지 않는다.

---

## 10. 시드 작업에서 발생한 문제와 조치

| # | 문제 | 조치 |
|---|---|---|
| 1 | 초안이 파티션 범위 안이라는 이유로 **미래 업무일자**(20260812~20260826) 이력을 만들었다. 오늘이 20260806 이므로 존재할 수 없는 스냅샷이다 | `history_dates()` 를 현재 업무일자로 상한 처리. 품질 게이트 테스트로 고정 |
| 2 | `site_policy` 계산에서 `if-else` 양쪽이 같은 값을 반환하는 죽은 조건식을 썼다 (ruff RUF034) | 단순화 |
