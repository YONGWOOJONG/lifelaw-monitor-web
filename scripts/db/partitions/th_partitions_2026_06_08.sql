-- TH_CRAWL_TARGET 월 파티션 (개발 DB)
--
-- 근거: create_c_schema_v2_19.sql 헤더 —
--   "TH_CRAWL_TARGET monthly partitions must be created separately for the
--    current business month and previous two calendar months before history
--    rows are written. A future partition may be pre-created and does not
--    extend D-30's logical baseline window."
--
-- 기준 시점: 2026-08-06 (Asia/Seoul) → 현재 업무월 2026-08 + 직전 2개 달
--
-- 파티션 키는 batch_ymd CHAR(8) 문자열이다. 날짜 타입으로 캐스팅하지 않는다.
-- 경계는 [FROM, TO) 반열림 구간이므로 다음 달 1일이 상한이 된다.
--
-- 소유자는 수집기 소유 롤(lifelaw_collector_owner)이어야 한다. 테이블 소유자는
-- 컬럼 단위 GRANT를 우회하므로, Web 롤이 소유하면 권한 모델이 무의미해진다.
--
-- 이 스크립트는 non-idempotent다. 이미 존재하면 실패한다.

BEGIN;

CREATE TABLE th_crawl_target_2026_06
    PARTITION OF th_crawl_target
    FOR VALUES FROM ('20260601') TO ('20260701');

CREATE TABLE th_crawl_target_2026_07
    PARTITION OF th_crawl_target
    FOR VALUES FROM ('20260701') TO ('20260801');

CREATE TABLE th_crawl_target_2026_08
    PARTITION OF th_crawl_target
    FOR VALUES FROM ('20260801') TO ('20260901');

ALTER TABLE th_crawl_target_2026_06 OWNER TO lifelaw_collector_owner;
ALTER TABLE th_crawl_target_2026_07 OWNER TO lifelaw_collector_owner;
ALTER TABLE th_crawl_target_2026_08 OWNER TO lifelaw_collector_owner;

COMMIT;
