-- lifelaw-monitor-web : 승인 원장을 명령 밖으로 확장하는 마이그레이션 0002
--
-- 권위 : DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md (APPROVED)
--          §18  위험 등급별 승인
--          §9   관리 명령 Inbox (명령 타입 4종)
--          §7.2 TW_ 는 Web 이 유일한 작성자
--
-- 사유 : §18 은 **계정 권한 변경(최고)** 과 **사이트 정책 변경(고)** 에 승인을
--        요구한다. 그런데 0001 의 TW_APPROVAL.command_id 는 NOT NULL 이고
--        TW_ADMIN_COMMAND 를 참조한다. §9 의 명령 타입은
--        RERUN_BATCH / CANCEL_BATCH / RESET_TARGET / RESYNC_R_MASTER 4종뿐이라
--        계정도 사이트 정책도 명령이 아니다(정책 변경은 §10 이 Inbox 가 아닌
--        별도 트랜잭션 절차로 정의한다).
--
--        결과적으로 §18 이 승인을 요구하는 두 영역 모두 승인을 기록할 자리가
--        없었다. C-1(컬럼 소유권 드리프트)과 같은 부류의 설계 공백이며,
--        사용자 결정(2026-08-07)에 따라 스키마를 넓혀 해소한다.
--
-- 방식 : command_id 를 NULL 허용으로 바꾸고 target_type / target_id 를 더한다.
--        이름은 TW_AUDIT_LOG 의 같은 개념(target_type / target_id)과 맞췄다.
--        승인 한 건은 **명령 하나 또는 대상 하나**를 가리키며 둘 다이거나
--        둘 다 아닌 행은 CHECK 로 막는다. 그래야 "무엇을 승인했는가"가
--        원장만 보고 항상 하나로 정해진다.
--
-- 유지 : 4-eyes(ck_tw_approval_four_eyes)와 CRITICAL 재인증 강제
--        (ck_tw_approval_critical_reauth)는 그대로 둔다. 이 마이그레이션은
--        승인의 **대상 범위**만 넓히고 승인의 **조건**은 건드리지 않는다.
--
-- 성격 : non-idempotent. 이미 적용됐으면 실패한다. 재적용하지 않는다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 명령이 아닌 승인을 허용한다
-- ---------------------------------------------------------------------------

ALTER TABLE TW_APPROVAL ALTER COLUMN command_id DROP NOT NULL;

ALTER TABLE TW_APPROVAL ADD COLUMN target_type VARCHAR(50);
ALTER TABLE TW_APPROVAL ADD COLUMN target_id   VARCHAR(100);

COMMENT ON COLUMN TW_APPROVAL.command_id IS
  '승인 대상이 관리 명령일 때만 채운다. 계정·정책 승인은 NULL 이고 target_* 를 쓴다';
COMMENT ON COLUMN TW_APPROVAL.target_type IS
  '명령이 아닌 승인 대상의 종류. 예: USER / USER_ROLE / ROLE / ROLE_PERMISSION / SITE_POLICY';
COMMENT ON COLUMN TW_APPROVAL.target_id IS
  '대상 식별자. user_id 나 role_cd 처럼 타입이 제각각이라 문자열로 둔다';

-- ---------------------------------------------------------------------------
-- 2. 승인 한 건은 정확히 하나를 가리킨다
--
-- 둘 다 채우면 "명령을 승인한 것인지 계정을 승인한 것인지" 원장만으로 판정할
-- 수 없고, 둘 다 비우면 무엇을 승인했는지 알 수 없다. 애플리케이션 규율에
-- 맡기지 않고 DB 에서 막는다.
-- ---------------------------------------------------------------------------

ALTER TABLE TW_APPROVAL ADD CONSTRAINT ck_tw_approval_target CHECK (
    (command_id IS NOT NULL AND target_type IS NULL AND target_id IS NULL)
 OR (command_id IS NULL AND target_type IS NOT NULL AND target_id IS NOT NULL)
);

CREATE INDEX ix_tw_approval_target ON TW_APPROVAL (target_type, target_id);

COMMIT;
