-- lifelaw-monitor-web : 런타임 롤 권한 부여
--
-- 권위 : DESIGN_project_structure_and_toolchain_v0_1.md §7
--        docs/contracts/db-contract.md §2.8 (쓰기 allowlist) / §2.9 (금지 컬럼)
--        DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7.1 §7.2 §15
--
-- 핵심 : PostgreSQL 의 컬럼 단위 GRANT UPDATE 로 "실행 상태 컬럼 직접 수정
--        금지"를 애플리케이션 규율이 아니라 DB 권한으로 강제한다. 코드에
--        버그가 있어도 crawl_stat_cd 에 대한 UPDATE 는 DB 가 거부한다.
--
--        같은 원리로 TW_AUDIT_LOG 에 UPDATE/DELETE 를 부여하지 않아
--        append-only 가 애플리케이션 밖에서 보장된다.
--
-- 전제 : 수집기 소유 테이블의 소유자는 lifelaw_collector_owner 여야 한다.
--        테이블 소유자는 컬럼 단위 GRANT 를 우회하므로, Web 롤이 소유하면
--        이 파일의 통제가 전부 무의미해진다.
--
-- 적용 : 소유자 권한이 필요하므로 DB 소유자로 실행한다. 애플리케이션은 이
--        스크립트를 실행하지 않는다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 기본 차단 (default-deny)
-- ---------------------------------------------------------------------------

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM lifelaw_web_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM lifelaw_web_app;

-- ---------------------------------------------------------------------------
-- 2. 수집기 소유 테이블 — 조회는 전체, 쓰기는 정책 컬럼만
-- ---------------------------------------------------------------------------

GRANT SELECT ON TC_COMMON_CODE         TO lifelaw_web_app;
GRANT SELECT ON TN_CNPCLS_CNLNK        TO lifelaw_web_app;
GRANT SELECT ON TH_CRAWL_TARGET        TO lifelaw_web_app;
GRANT SELECT ON TN_BATCH_RUN           TO lifelaw_web_app;
GRANT SELECT ON TN_CRAWL_TARGET        TO lifelaw_web_app;
GRANT SELECT ON TN_COLLECT_SITE_POLICY TO lifelaw_web_app;

-- 대상 직접 정책. 계약 §2.8 allowlist 와 정확히 일치해야 한다.
--
-- target_collect_policy_cd 와 collect_target_kind_cd 는 DDL 제약
-- ck_crawl_target_direct_kind 때문에 항상 함께 갱신해야 한다.
GRANT UPDATE (
    target_collect_policy_cd,
    collect_target_kind_cd,
    target_policy_version,
    mod_dt
) ON TN_CRAWL_TARGET TO lifelaw_web_app;

-- 사이트 정책. reger 는 부여하지 않는다(등록자는 최초 1회이며 변경 대상이 아님).
GRANT UPDATE (
    collect_policy_cd,
    policy_version,
    policy_reason,
    moder,
    mod_dt
) ON TN_COLLECT_SITE_POLICY TO lifelaw_web_app;

-- 사이트 정책 신규 등록은 허용한다. 시퀀스 사용 권한이 함께 필요하다.
GRANT INSERT ON TN_COLLECT_SITE_POLICY TO lifelaw_web_app;
GRANT USAGE, SELECT ON SEQUENCE tn_collect_site_policy_site_policy_id_seq
    TO lifelaw_web_app;

-- ---------------------------------------------------------------------------
-- 3. Web 소유 테이블
-- ---------------------------------------------------------------------------

-- 계정·RBAC — 일반 CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON TW_USER            TO lifelaw_web_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TW_ROLE            TO lifelaw_web_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TW_PERMISSION      TO lifelaw_web_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TW_ROLE_PERMISSION TO lifelaw_web_app;
GRANT SELECT, INSERT, DELETE         ON TW_USER_ROLE       TO lifelaw_web_app;
GRANT USAGE, SELECT ON SEQUENCE tw_user_user_id_seq TO lifelaw_web_app;

-- 세션 — 설계 §7.2 는 C·R·D 를 부여한다. 그러나 §17.4 의 유휴 만료(30분)는
-- 요청마다 last_seen_at 갱신을 요구한다. 두 요구를 함께 만족시키기 위해
-- UPDATE 를 두 컬럼으로만 한정한다. 세션 소유자(user_id)나 만료 시각을
-- 사후 변경하는 경로는 열지 않는다.
GRANT SELECT, INSERT, DELETE ON TW_SESSION TO lifelaw_web_app;
GRANT UPDATE (last_seen_at, reauth_at) ON TW_SESSION TO lifelaw_web_app;

-- 명령 Inbox — Web 은 PENDING 을 INSERT 한다. 상태 전이는 소비자 소관이지만,
-- Web 은 자기 권한으로 REJECTED(승인 거부)와 EXPIRED 를 쓸 수 있어야 한다
-- (설계 §9). 따라서 UPDATE 를 status·approved_by·result_msg·mod_dt 로 한정한다.
GRANT SELECT, INSERT ON TW_ADMIN_COMMAND TO lifelaw_web_app;
GRANT UPDATE (status, approved_by, result_msg, mod_dt)
    ON TW_ADMIN_COMMAND TO lifelaw_web_app;
GRANT USAGE, SELECT ON SEQUENCE tw_admin_command_command_id_seq TO lifelaw_web_app;

-- 승인 원장 — append-only
GRANT SELECT, INSERT ON TW_APPROVAL TO lifelaw_web_app;
GRANT USAGE, SELECT ON SEQUENCE tw_approval_approval_id_seq TO lifelaw_web_app;

-- 감사 로그 — append-only. UPDATE/DELETE 를 절대 부여하지 않는다.
GRANT SELECT, INSERT ON TW_AUDIT_LOG TO lifelaw_web_app;
GRANT USAGE, SELECT ON SEQUENCE tw_audit_log_audit_id_seq TO lifelaw_web_app;

-- 마이그레이션 원장 — 애플리케이션은 기대 버전 확인을 위해 읽기만 한다.
GRANT SELECT ON TW_SCHEMA_MIGRATION TO lifelaw_web_app;

COMMIT;
