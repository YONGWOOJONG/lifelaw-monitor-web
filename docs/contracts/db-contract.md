---
Document-ID: CONTRACT-LIFELAW-MONITOR-WEB-DB
Version: 0.1
Status: PROPOSAL
Authority: ADVISORY
Implementation-Authority: false
Owner: User
Depends-On: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md (v1.2, APPROVED)
---

# 저장소 간 DB 계약 (G-1) — v0.1

> **이 문서는 `PROPOSAL`이며 구현 권위가 아니다.** 다만 아래 §2의 스키마 사실은
> 참조 저장소의 실제 DDL 파일을 읽어 확인한 **사실**이며, 제안과 구분한다.
>
> 상위 권위는 `DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md` §21이다.

---

## 1. 계약 버전 핀

이 저장소는 아래 버전에 의존한다. **핀을 갱신하지 않은 채 새 컬럼·새 코드값에
의존하지 않는다.**

```text
참조 저장소      : lifelaw-monitor
참조 문서        : C1 v2.20  (docs/data/schema/C1_schema_v2_20.md, APPROVED)
물리 DDL         : scripts/db/create_c_schema_v2_19.sql
코드 정의        : G1 v3.14
관련 ADR         : D-25 기준선 선택, D-28 수집 제외/POLICY_BARRIER,
                   D-26 시간 계약, D-27 PostgreSQL 18, D-30 보존,
                   D-31 PDF 상세, D-32 HTTPS 후보 비적용
확인 시점        : 2026-08-06 (Asia/Seoul)
확인 방법        : DDL 파일 직접 판독 + docs/governance-index.md 활성 등록분 대조
DDL SHA-256      : 3b8fbfa14fa396b4e75996558aad2e18c6fd2c0007501d3bef37f49bfc7db9fa
```

C1 문서 버전(2.20)과 DDL 파일 버전(2.19)이 다른 것은 **정상이다.** 참조 저장소
governance-index는 "C DDL/create-only v2.19 불변"으로 기록하고 있다. 즉 C1 2.20
개정은 DDL을 변경하지 않았다.

**DDL 사본을 이 저장소에 두지 않는다.** 참조 저장소 파일을 읽기 전용으로 적용하고,
위 SHA-256으로 동일성을 확인한다. 사본을 두면 원본 개정 시 조용히 갈라진다.

### 1.1 v2_18 / v2_19 동일성 (확인 사실)

두 파일은 **본문 DDL이 바이트 단위로 동일**하고 차이는 헤더 주석뿐이다.

```text
create_c_schema_v2_18.sql  dec2b162c030f6dd27a3b9f0115107758812abd2e76923c03dc9ab84319bc95e
create_c_schema_v2_19.sql  3b8fbfa14fa396b4e75996558aad2e18c6fd2c0007501d3bef37f49bfc7db9fa

차이: Authority 주석(v2_18 → v2_19, D-30 추가)과 파티션 생성 범위 설명 3줄
```

따라서 어느 쪽을 적용해도 스키마 결과는 같다. 다만 **활성 등록본은 v2_19이므로
v2_19를 적용하고 위 해시를 기록한다.**

### 1.2 TH_CRAWL_TARGET 파티션 요구 (v2_19 헤더 명시)

> "TH_CRAWL_TARGET monthly partitions must be created separately for the
> **current business month and previous two calendar months** before history
> rows are written. A future partition may be pre-created and does not extend
> D-30's logical baseline window."

- DDL은 파티션을 만들지 않는다. **별도로 3개 월 파티션을 만들어야 한다**
- 미래 파티션 선생성은 허용되지만 **D-30의 논리적 기준선 윈도우를 넓히지
  않는다.** 즉 파티션이 있다고 4개월 전 데이터를 조회할 수 있다는 뜻이 아니다
- 파티션 키는 `batch_ymd CHAR(8)` **문자열**이다. 경계는 `'20260801'` 형태의
  문자열 리터럴로 지정한다. 날짜 타입 캐스팅을 끼우지 않는다

## 2. 의존 스키마 사실

DDL 판독 결과다. 추론이 아니다.

### 2.1 테이블 6개

| 테이블 | PK | 성격 | Web 접근 |
|---|---|---|---|
| `TC_COMMON_CODE` | (`code_grp_cd`, `code_val`) | 코드 사본 | SELECT only |
| `TN_COLLECT_SITE_POLICY` | `site_policy_id` (IDENTITY) | 사이트 정책 | SELECT + 정책 컬럼 UPDATE (명령 경유) |
| `TN_CNPCLS_CNLNK` | `con_link_seq` | R 마스터 사본 | SELECT only |
| `TN_CRAWL_TARGET` | `url_id` | 현재 상태 | SELECT + 정책 컬럼 UPDATE (명령 경유) |
| `TH_CRAWL_TARGET` | (`url_id`, `batch_ymd`) | 이력 스냅샷 | SELECT only |
| `TN_BATCH_RUN` | `run_id` (IDENTITY) | 실행 원장 | SELECT only |

`TH_CRAWL_TARGET`은 `PARTITION BY RANGE (batch_ymd)`다. **DDL에 파티션 자체는
생성되어 있지 않다.** 월 파티션 생성은 참조 저장소의 배포 게이트 사항이다.
따라서 파티션이 없는 기간을 조회하면 결과가 0건이 되며, 이는 데이터 유실이
아니다. UI는 이를 구분해 표시한다.

### 2.2 계산 컬럼 — TN에서만 GENERATED

`TN_CRAWL_TARGET`

```sql
effective_collect_policy_cd  GENERATED ALWAYS AS (
  CASE WHEN site_collect_policy_cd = '7020'
         OR target_collect_policy_cd = '7020'
       THEN '7020' ELSE '7010' END) STORED

execution_collect_policy_cd  GENERATED ALWAYS AS (
  CASE WHEN site_collect_policy_cd = '7020'
         OR target_collect_policy_cd = '7020'
         OR run_collect_policy_cd   = '7020'      -- ← run 항이 추가된다
       THEN '7020' ELSE '7010' END) STORED
```

**두 컬럼의 차이는 `run_collect_policy_cd` 항 하나다.** `effective`는 구성
정책만, `execution`은 실행 시점 제외까지 반영한다. 화면에서 두 값을 혼용하면
"제외인데 제외가 아닌" 표시가 나온다.

`TH_CRAWL_TARGET`에서는 같은 두 컬럼이 **GENERATED가 아니다.** 일반 `NOT NULL`
컬럼이고, 동일한 수식을 `CHECK` 제약(`ck_h_crawl_target_config_policy`,
`ck_h_crawl_target_execution_effective`)으로 강제한다.

> **Web 규칙.** TN·TH 모두에서 이 두 컬럼은 **읽기 전용**이다. 프론트엔드에서
> OR 규칙을 재구현하지 않는다. 재구현하면 수식이 바뀔 때 드리프트가 생긴다.

### 2.3 CHECK 제약 — Web 쓰기에 직접 영향

| 제약 | 내용 | Web에 대한 함의 |
|---|---|---|
| `ck_crawl_target_site_binding` | `site_policy_id IS NULL` → `site_collect_policy_cd='7010'` AND `site_policy_version=0`. 아니면 `site_policy_id NOT NULL` AND `site_policy_version>=1` | 사이트 정책 연결과 버전을 따로 갱신할 수 없다 |
| `ck_crawl_target_direct_kind` | `collect_target_kind_cd IS NULL` → `target_collect_policy_cd='7010'`. `7110`↔`link_class_cd='901001'`, `7120`↔`'901002'` | **대상 직접 제외(7020) 시 종류 코드가 필수**이고 링크 분류와 일치해야 한다 |
| `ck_crawl_target_run_exclusion` | `run_collect_policy_cd='7010'` → 제외 사이트 ID NULL·버전 0. `'7020'` → ID NOT NULL·버전>=1 | 3개 컬럼이 묶여 있다. Web은 이 묶음을 쓰지 않는다 |
| `ck_crawl_target_diag` | 3컬럼 all-or-none **이면서**, 값이 있을 때 `crawl_diag_cd IN ('8010','8020')` AND `crawl_diag_msg` 비어있지 않음 AND `crawl_candidate_url LIKE 'https://%'` AND **`crawl_stat_cd='1090'`** AND **`change_yn_cd='5000'`** | 진단 컬럼은 상태 컬럼 2개와도 묶여 있다. 부분 초기화는 제약 위반이 된다 |
| `ck_collect_site_policy` / `ck_crawl_target_*_policy` | 정책 코드는 `'7010'`/`'7020'`만 | 다른 값 제출은 DB가 거부 |
| `ck_collect_site_version` | `policy_version >= 1` | 사이트 정책 버전은 1부터 |

`TH_CRAWL_TARGET`에도 동일 취지의 제약이 `ck_h_*` 이름으로 존재한다.

### 2.4 행위자 귀속 컬럼의 비대칭 — 확인된 사실

| 테이블 | `reger` / `moder` |
|---|---|
| `TN_COLLECT_SITE_POLICY` | **있음** (`VARCHAR(100) NOT NULL` 둘 다) |
| `TN_CNPCLS_CNLNK` | 있음 (`VARCHAR(20) NOT NULL`) |
| `TN_CRAWL_TARGET` | **없음** — `reg_dt`/`mod_dt`만 |
| `TH_CRAWL_TARGET` | 없음 — `snap_dt`만 |
| `TN_BATCH_RUN` | 없음 — `reg_dt`만 |

상위 설계 §19.1의 지적이 사실로 확인됐다. **대상 직접 정책 변경은 수집기 스키마
안에서 행위자 귀속이 불가능하다.** A-06 1안(`TW_AUDIT_LOG`가 행위자 원장)이
기본 동작이다.

사이트 정책은 `reger`/`moder`가 `NOT NULL`이므로, Web이 정책을 변경할 때
**`moder`에 실제 관리자 식별자를 반드시 넣어야 한다.** 고정 문자열이나 DB 계정명을
넣으면 감사 가치가 사라진다.

### 2.5 기본값 주의

| 컬럼 | DEFAULT | 주의 |
|---|---|---|
| `TN_COLLECT_SITE_POLICY.collect_policy_cd` | **`'7020'`** (수집제외) | 사이트 정책 행을 만들면 기본이 **제외**다. UI는 이 기본값을 명시적으로 보여준다 |
| `TN_CRAWL_TARGET.site_collect_policy_cd` | `'7010'` | |
| `TN_CRAWL_TARGET.target_collect_policy_cd` | `'7010'` | |
| `TN_CRAWL_TARGET.run_collect_policy_cd` | `'7010'` | |
| `TN_CRAWL_TARGET.crawl_stat_cd` | `'1010'` | |
| `TN_CRAWL_TARGET.extract_stat_cd` | `'2000'` | 비대상 |
| `TN_CRAWL_TARGET.norm_stat_cd` | `'3000'` | 비대상 |
| `TN_CRAWL_TARGET.cmpr_stat_cd` | `'4000'` | 비대상 |
| `TN_CRAWL_TARGET.change_yn_cd` | `'5000'` | 미확인 |
| `TN_BATCH_RUN.run_stat_cd` | `'6010'` | 대기 |
| `TC_COMMON_CODE.use_yn` | `'Y'` | Web은 이 값을 바꾸지 않는다 |

### 2.6 의존 코드값 — DDL seed 기준 33건

```text
CRAWL_STAT           1010 1020 1090
EXTRACT_STAT         2000 2010 2020 2090
NORM_STAT            3000 3010 3020 3090
CMPR_STAT            4000 4010 4020
CHANGE_YN            5000 5001 5010 5020 5030 5040
RUN_STAT             6010 6020 6030 6040 6080 6090
COLLECT_POLICY       7010 7020
COLLECT_TARGET_KIND  7110 7120
CRAWL_DIAG           8010 8020
LINK_CLASS           901001 901002
```

코드 그룹명은 `COLLECT_TARGET_KIND`다(`TARGET_KIND`가 아니다). 라벨은
`code_nm`을 쓰고, `code_const`는 코드 상수명이다.

`5001`(기준선 설정)은 신규 등록·강제 재기준선·성공 기준선 부재를 포함한다.
**변경 감지 건수에 합산하지 않는다.**

### 2.7 시간과 일자

- 12개 instant 컬럼은 `TIMESTAMPTZ(3)` (D-26)
- `batch_ymd`는 `CHAR(8)` 서울 업무일자. 타임스탬프가 아니다
- 지역시각 provenance는 `Asia/Seoul`
- **세션 타임존에 의존하는 쿼리를 쓰지 않는다.** 연결 시 세션 TZ를 명시 고정하고,
  일자 경계 계산은 `batch_ymd` 문자열 비교로 처리한다

### 2.8 Web이 쓰기 가능한 컬럼 — allowlist

이 목록 밖의 컬럼에 대한 UPDATE 경로를 만들지 않는다.

```text
TN_COLLECT_SITE_POLICY
  collect_policy_cd
  policy_version
  policy_reason
  moder, mod_dt

TN_CRAWL_TARGET
  target_collect_policy_cd
  collect_target_kind_cd
  target_policy_version
  mod_dt
```

**§2.3의 `ck_crawl_target_direct_kind` 때문에 `target_collect_policy_cd`와
`collect_target_kind_cd`는 항상 같은 문장에서 함께 갱신해야 한다.**

사이트 정책 변경 시 하위 대상의 `site_collect_policy_cd`·`site_policy_id`·
`site_policy_version` 재정합은 **D-28 계약 절차가 같은 트랜잭션에서 수행한다.**
Web이 이 컬럼을 별도 문장으로 갱신하지 않는다.

### 2.9 Web이 절대 쓰지 않는 컬럼

```text
실행 상태   crawl_stat_cd  extract_stat_cd  norm_stat_cd  cmpr_stat_cd
            change_yn_cd
오류        crawl_err_msg  extract_err_msg  norm_err_msg  cmpr_err_msg
            change_err_msg
해시        raw_html_hash  norm_html_hash  prev_raw_hash  prev_norm_hash
진단        crawl_diag_cd  crawl_diag_msg  crawl_candidate_url
파일        file_size  file_mtime  file_format_cd
방법        extract_method_cd
일자        batch_ymd
실행 제외   run_collect_policy_cd
            run_exclusion_site_policy_id
            run_exclusion_site_policy_version
계산        effective_collect_policy_cd  execution_collect_policy_cd
사이트 상속 site_policy_id  site_collect_policy_cd  site_policy_version
전체        TH_CRAWL_TARGET 모든 컬럼
            TN_BATCH_RUN 모든 컬럼
            TN_CNPCLS_CNLNK 모든 컬럼
            TC_COMMON_CODE 모든 컬럼 (use_yn 포함)
```

> **드리프트 발견.** 상위 설계 v1.1 §7.1의 "절대 쓰지 않는 컬럼" 목록에는
> `run_collect_policy_cd`, `run_exclusion_site_policy_id`,
> `run_exclusion_site_policy_version`, `file_format_cd`, `extract_method_cd`가
> **빠져 있다.** DDL 판독으로 확인한 결과 이 5개는 모두 수집기 소유(D-28 redirect
> 실행 제외 영속성, D-31 PDF 추출 방법)다. 이 문서가 완전한 목록이며, 상위 설계의
> 다음 개정에 반영이 필요하다. §5에 미결로 기록한다.

## 3. fail-closed 기동 검증 항목

기동 시 아래를 검사하고, **하나라도 실패하면 기능을 열지 않고 기동을
실패시킨다.** 조용한 폴백을 만들지 않는다.

| # | 검사 | 실패 시 |
|---|---|---|
| V-01 | 테이블 6개 존재 | 기동 실패 |
| V-02 | §2.8 allowlist 컬럼과 §2.9 금지 컬럼이 실제로 존재 (이름·타입) | 기동 실패 |
| V-03 | `TN_CRAWL_TARGET`의 두 계산 컬럼이 `attgenerated='s'`(STORED GENERATED) | 기동 실패 |
| V-04 | 계산 컬럼 수식에 `run_collect_policy_cd` 항의 유무가 §2.2와 일치 | 기동 실패 |
| V-05 | `TC_COMMON_CODE`에 §2.6의 코드값 33건이 모두 존재하고 `use_yn='Y'` | 기동 실패 |
| V-06 | `TH_CRAWL_TARGET`이 파티션 테이블(`relkind='p'`) | 기동 실패 |
| V-07 | `TH_CRAWL_TARGET`의 조회 가능 파티션 목록 확인 | 실패 아님. 조회 가능 범위로 UI에 전달 |
| V-08 | §2.3 CHECK 제약이 이름으로 존재 | 기동 실패 |
| V-09 | 런타임 롤이 `TW_AUDIT_LOG`에 UPDATE/DELETE 권한을 **갖지 않음** | 기동 실패 |
| V-10 | 런타임 롤의 `TN_CRAWL_TARGET` UPDATE 권한이 §2.8 컬럼으로 한정됨 | 기동 실패 |
| V-11 | `TW_SCHEMA_MIGRATION` 최신 버전이 코드가 기대하는 버전과 일치 | 기동 실패 |
| V-12 | 설정 JSON에 `user`/`password`/`secret` 키 부재 | 기동 실패 |

V-09·V-10은 `information_schema.column_privileges` / `table_privileges`로
확인한다. **권한 설계가 문서에만 있고 실제로 적용되지 않은 상태를 잡아내는
것이 목적이다.**

참조 저장소에도 동등한 `validate_schema()` 절차가 있으므로 같은 엄격도를 유지한다.

## 4. 계약 변경 절차

1. 참조 저장소 C1 또는 DDL이 개정되면 **먼저 이 문서의 핀을 갱신**한다
2. 핀 갱신과 함께 §2를 재판독한다. 기억이나 이전 요약에 의존하지 않는다
3. 영향 범위(V-01~V-12, allowlist, 화면)를 검토하고 필요한 코드를 함께 바꾼다
4. 핀 갱신 없이 새 컬럼·새 코드값에 의존하는 코드를 병합하지 않는다
5. 이 저장소에서 참조 저장소의 문서·DDL을 수정하지 않는다

## 5. 미결 사항

| # | 항목 | 필요 조치 |
|---|---|---|
| C-1 | 상위 설계 v1.1 §7.1의 금지 컬럼 목록에 5개 누락 (§2.9 드리프트) | 상위 설계 다음 개정에 반영. 사용자 승인 필요 |
| C-2 | 개발용 데이터베이스 이름 | DB 생성 시 결정 |
| C-3 | ~~`TH_CRAWL_TARGET` 월 파티션 생성 주체~~ | **해소** (2026-08-06 사용자 확인) — 개발 DB는 이 저장소가 생성한다. v2_19 헤더대로 현재 업무월 + 직전 2개 달 3개 파티션을 만든다. §1.2 |
| C-4 | 사이트 정책 `moder`에 넣을 관리자 식별자 형식 (로그인 ID? 사번?) | 인증 구현 시 |
| C-5 | 참조 저장소 D-26 "영속 PostgreSQL 사용자 테이블 없음" 기록과 `TW_` 신설의 불일치 | 참조 저장소 소관. 보고만 |

## 6. SELF-REFINE

| 공격 질문 | 판정 | 대응 |
|---|---|---|
| 스키마 사실을 설계 문서 요약에서 베껴 왔는가 | **아니다** | DDL 파일을 직접 판독했다. 그 결과 상위 설계에 없던 사실 5건(§2.9 드리프트)과 CHECK 제약의 실제 결합 범위를 찾았다 |
| `ck_crawl_target_diag`를 3컬럼 묶음으로만 이해했는가 | **수정함** | 실제로는 `crawl_stat_cd='1090'`·`change_yn_cd='5000'`까지 5개 조건이 묶인다. §2.3에 정정 기록 |
| TH의 계산 컬럼을 TN과 같다고 가정했는가 | **수정함** | TH는 GENERATED가 아니라 CHECK 강제다. §2.2에 구분 기록 |
| `effective`와 `execution`을 같은 것으로 취급하는가 | 통과 | §2.2에서 차이가 `run` 항 하나임을 명시. 혼용 금지 |
| allowlist가 CHECK 제약과 모순되는가 | **수정함** | `target_collect_policy_cd`만 바꾸면 `ck_crawl_target_direct_kind` 위반이 가능하다. §2.8에 "항상 함께 갱신" 규칙 추가 |
| 사이트 정책 기본값을 `7010`으로 가정했는가 | **수정함** | DDL 기본값은 `'7020'`(제외)다. §2.5에 기록 |
| 권한 설계가 실제 적용됐는지 검증하는가 | 통과 | V-09·V-10에서 `information_schema` 조회로 확인 |
| 파티션 부재를 데이터 유실로 오해할 여지가 있는가 | 통과 | §2.1과 V-07에서 구분. UI에 조회 가능 범위를 전달 |
