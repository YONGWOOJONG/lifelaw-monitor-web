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

모든 업무 테이블은 **비어 있다.** 수집기가 아직 실행되지 않았고, 이 저장소는
수집 데이터를 만들지 않는다.

| 테이블 | 행수 |
|---|---|
| `TC_COMMON_CODE` | 34 (DDL seed) |
| `TW_ROLE` / `TW_PERMISSION` / `TW_ROLE_PERMISSION` | 6 / 14 / 35 (마이그레이션 seed) |
| 그 외 전부 | 0 |

**관리자 계정이 없다.** 로그인 화면(S-01)을 만들기 전에 최초 `ADMIN` 계정
생성 절차가 필요하다(§6 미결).

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
| RB-1 | 최초 `ADMIN` 계정 생성 방법 — CLI 스크립트 / 마이그레이션 seed / 최초 기동 시 부트스트랩 중 선택 |
| RB-2 | `command:resync` 를 어느 역할에 부여할지. 설계에 대응 화면이 없어 현재 미부여 |
| RB-3 | `artifact:read` 는 A-08 미승인이라 미부여. 승인 시 부여 대상 결정 |
| RB-4 | 세션 유휴 30분 / 절대 12시간은 제안값. 운영 확정 필요 |
| RB-5 | 월 파티션 자동 생성 방식(수동 스크립트 유지 vs 배치) |

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
