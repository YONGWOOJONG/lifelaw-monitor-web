# lifelaw-monitor-web 문서

생활법령 모니터링 **관리자 Web**(React UI + FastAPI 관리 백엔드)의 문서
디렉터리다. 수집 배치인 `lifelaw-monitor`와는 독립된 저장소·배포 단위이며,
연동은 승인된 PostgreSQL 데이터 계약을 통해서만 이루어진다.

## ⚠️ 현재 상태

**활성 설계 문서는 v1.2 `APPROVED`이며, 구현 권위는 승인된 항목으로 한정된다.**

2026-08-06 사용자 승인으로 **A-01·A-02·A-03·A-04·A-05·A-09** 6건이 확정됐다.
스택(FastAPI + React/Vite), 인증(서버 측 세션), Web 소유 `TW_` 테이블 7종,
역할 6종·권한 14종, 명명 규칙이 여기 포함된다.

미승인은 **A-06**(감사 행위자 귀속 — 1안이 기본 동작), **A-07**(명령 Inbox
소비자 구현 주체), **A-08**(아티팩트 열람 정책) 3건이며, 3·4단계 조회 MVP를
차단하지 않는다.

승인 상태의 **단일 출처**는 설계 문서 §23.1 표다. 본문 다른 절과 충돌하면
그 표가 우선한다.

현재 승인된 ADR은 **없다.** 문서 안의 ADR 후보 번호는 임시 라벨이며 최종 번호를
선점하지 않는다.

## 문서 목록

| 문서 | 상태 | 권위 | 내용 |
|---|---|---|---|
| [DESIGN_..._v1_2.md](architecture/designs/DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md) | **`APPROVED`** (활성) | `IMPLEMENTATION` (`Implementation-Authority=true`, 승인 항목 한정) | 관리자 Web 전체 아키텍처 — 저장소 분리, Shared Database Contract, 테이블 소유권, 단일 작성자 원칙, 관리 명령 Inbox, RBAC, 세션 인증, 감사, 단계별 구현 계획 |
| [DESIGN_admin_screen_inventory_v0_1.md](architecture/designs/DESIGN_admin_screen_inventory_v0_1.md) | `PROPOSAL` | `ADVISORY` (`Implementation-Authority=false`) | 관리자 화면 목록(G-2) 21개 — 화면별 데이터 소스·권한·위험 등급·종속 승인, 화면-권한 매트릭스, 제공하지 않는 화면 금지 목록 |
| [contracts/db-contract.md](contracts/db-contract.md) | `PROPOSAL` | `ADVISORY` (`Implementation-Authority=false`) | 저장소 간 DB 계약(G-1) — 계약 버전 핀, DDL 실측 스키마 사실, 쓰기 allowlist, 금지 컬럼, fail-closed 기동 검증 12항목 |
| [runbooks/dev-database-setup.md](runbooks/dev-database-setup.md) | `PROPOSAL` | `ADVISORY` (`Implementation-Authority=false`) | 개발 DB 구성 러너북 — 재현 절차, 실측 검증 결과, 재구성 방법, 실행 중 발생한 문제와 조치 |
| [DESIGN_project_structure_and_toolchain_v0_1.md](architecture/designs/DESIGN_project_structure_and_toolchain_v0_1.md) | `PROPOSAL` | `ADVISORY` (`Implementation-Authority=false`) | 프로젝트 구조·툴체인(G-4) — 디렉터리 레이아웃, ORM 배제 근거, 의존성 핀, 설정·secret 계약, DB 롤과 컬럼 단위 GRANT, 마이그레이션 방식 |
| [DESIGN_..._v1_0.md](architecture/designs/DESIGN_lifelaw_monitor_web_admin_architecture_v1_0.md) | `SUPERSEDED` | `ADVISORY` | A-03·A-05·A-09 승인 이전 상태 기록 |
| [DESIGN_..._v0_1.md](architecture/designs/DESIGN_lifelaw_monitor_web_admin_architecture_v0_1.md) | `SUPERSEDED` | `ADVISORY` | 최초 제안 상태 기록 |

## 권위 순서

운영 규칙과 권위 순서는 저장소 루트의 [AGENTS.md](../AGENTS.md)를 따른다.

```text
1. 사용자 명시 승인
2. 이 저장소에서 승인된 ADR
3. 승인된 용어·코드 정의
4. 승인된 데이터베이스 계약
5. 승인된 보안·RBAC 계약
6. 승인된 컴포넌트 명세
7. DESIGN, RESEARCH, PROMPT 문서
8. 과거·보관 문서
```

승인된 항목(A-01·A-02·A-04)에 대해서는 v1.0이 1순위(사용자 명시 승인)의
기록물로 작동하고, 미승인 항목은 7순위에 머문다.

## 다음 승인 대기 항목

설계 문서 §23.1이 승인 상태의 단일 출처다. 현재 미승인 3건.

| # | 항목 | 막고 있는 것 |
|---|---|---|
| A-06 | 대상 정책 변경의 행위자 귀속 1안/2안 | 없음 — 1안(`TW_AUDIT_LOG`)이 기본 동작 |
| A-07 | 명령 Inbox 소비자 구현 주체 | 6·7단계 (수집기 저장소 변경 수반) |
| A-08 | 아티팩트 열람 범위·원문 노출 정책 | S-07 아티팩트 뷰어 화면 |

**1·2단계가 모두 열려 있다.** 첫 릴리스 목표는 3·4단계 조회 MVP다.

## 원격 저장소

사용자 결정(2026-08-06)으로 **원격 저장소 작업은 전면 보류**다. 저장소 생성,
remote 추가, push, 원격 default branch 설정, branch protection을 수행하지
않는다. 로컬 기본 checkout은 `feature`다.

## 참조 저장소

`lifelaw-monitor`는 **읽기 전용 참조**다. 해당 저장소의 파일을 수정하지 않으며,
private instruction·session log·plan·memory를 반입하지 않는다. 저장소 간에는
사용자 승인을 받은 공개 중립 산출물만 공유한다.

참조 시점의 활성 공개 문서 버전은 설계 문서 상단 배너와 §21에 고정해 두었다.
원본이 개정되면 사본 요약은 무효이며, 버전 핀을 갱신하고 영향을 재검토한다.
