# lifelaw-monitor-web 문서

생활법령 모니터링 **관리자 Web**(React UI + FastAPI 관리 백엔드)의 문서
디렉터리다. 수집 배치인 `lifelaw-monitor`와는 독립된 저장소·배포 단위이며,
연동은 승인된 PostgreSQL 데이터 계약을 통해서만 이루어진다.

## ⚠️ 현재 상태

**이 디렉터리의 모든 문서는 `PROPOSAL`이며 구현 권위가 아니다.**

사용자 명시 승인 전까지 아래 문서를 근거로 코드, 스키마, 권한, 저장소 간
계약을 확정하지 않는다. 승인 전 상태에서 문서 내용을 "확정 사항"으로 인용하는
것도 금지한다.

현재 승인된 ADR은 **없다.** 문서 안의 ADR 후보 번호는 임시 라벨이며 최종 번호를
선점하지 않는다.

## 문서 목록

| 문서 | 상태 | 권위 | 내용 |
|---|---|---|---|
| [DESIGN_lifelaw_monitor_web_admin_architecture_v0_1.md](architecture/designs/DESIGN_lifelaw_monitor_web_admin_architecture_v0_1.md) | `PROPOSAL` | `ADVISORY` (`Implementation-Authority=false`) | 관리자 Web 전체 아키텍처 — 저장소 분리, Shared Database Contract, 테이블 소유권, 단일 작성자 원칙, 관리 명령 Inbox, RBAC, 감사, 단계별 구현 계획 |

## 권위 순서

운영 규칙과 권위 순서는 저장소 루트의 [AGENTS.md](../AGENTS.md)를 따른다.

```text
1. 사용자 명시 승인
2. 이 저장소에서 승인된 ADR
3. 승인된 용어·코드 정의
4. 승인된 데이터베이스 계약
5. 승인된 보안·RBAC 계약
6. 승인된 컴포넌트 명세
7. DESIGN, RESEARCH, PROMPT 문서   ← 현재 문서는 여기
8. 과거·보관 문서
```

## 다음 승인 대기 항목

설계 문서 §23에 승인 필요 사항 9건(A-01 ~ A-09)이 정리되어 있다. 주요 항목은
다음과 같다.

- 이 설계 문서의 승인 상태 승격
- FastAPI + React/Vite 스택 확정
- Web 소유 테이블 신설 (인증·RBAC·감사·명령 원장)
- 인증 방식 결정
- 대상 정책 변경의 행위자 귀속 방식 결정

## 참조 저장소

`lifelaw-monitor`는 **읽기 전용 참조**다. 해당 저장소의 파일을 수정하지 않으며,
private instruction·session log·plan·memory를 반입하지 않는다. 저장소 간에는
사용자 승인을 받은 공개 중립 산출물만 공유한다.

참조 시점의 활성 공개 문서 버전은 설계 문서 상단 배너와 §21에 고정해 두었다.
원본이 개정되면 사본 요약은 무효이며, 버전 핀을 갱신하고 영향을 재검토한다.
