-- lifelaw-monitor-web : DB 계약 fail-closed 검증
--
-- 근거 : docs/contracts/db-contract.md §3 (V-01 ~ V-12)
--
-- 이 스크립트는 소유자 권한으로 실행해 현황을 보고한다. 애플리케이션 기동 시의
-- 실제 fail-closed 검증은 src/lifelaw_web/db/schema_check.py 가 담당하며,
-- 이 파일은 그 기대값의 근거이자 운영자용 점검 도구다.
--
-- V-09/V-10 은 권한 설계가 문서에만 있고 실제로 적용되지 않은 상태를 잡아내는
-- 것이 목적이다. 권한 부여 스크립트를 실행했다는 사실만으로는 증거가 아니다.

\pset footer off
\timing off

\echo '=== V-01  테이블 6개 존재 (기대 6) ==='
SELECT count(*) AS c_tables
  FROM pg_tables
 WHERE schemaname = 'public'
   AND tablename IN ('tc_common_code','tn_collect_site_policy','tn_cnpcls_cnlnk',
                     'tn_crawl_target','th_crawl_target','tn_batch_run');

\echo '=== V-02  allowlist 컬럼 존재 (기대 9) ==='
SELECT count(*) AS allowlist_cols
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND (   (table_name = 'tn_crawl_target'
            AND column_name IN ('target_collect_policy_cd','collect_target_kind_cd',
                                'target_policy_version','mod_dt'))
        OR (table_name = 'tn_collect_site_policy'
            AND column_name IN ('collect_policy_cd','policy_version',
                                'policy_reason','moder','mod_dt')));

\echo '=== V-03  TN 계산 컬럼이 STORED GENERATED (기대 2행, 모두 s) ==='
SELECT attname, attgenerated
  FROM pg_attribute
 WHERE attrelid = 'tn_crawl_target'::regclass
   AND attname IN ('effective_collect_policy_cd','execution_collect_policy_cd')
 ORDER BY attname;

\echo '=== V-04  계산 컬럼 수식에 run 항 유무 (effective=false, execution=true) ==='
SELECT a.attname,
       pg_get_expr(d.adbin, d.adrelid) LIKE '%run_collect_policy_cd%' AS has_run_term
  FROM pg_attribute a
  JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
 WHERE a.attrelid = 'tn_crawl_target'::regclass
   AND a.attname IN ('effective_collect_policy_cd','execution_collect_policy_cd')
 ORDER BY a.attname;

\echo '=== V-05  공통 코드 그룹별 건수와 use_yn (기대 합계 34, 전부 Y) ==='
SELECT code_grp_cd, count(*) AS cnt, count(*) FILTER (WHERE use_yn <> 'Y') AS not_used
  FROM tc_common_code GROUP BY code_grp_cd ORDER BY min(sort_ord), code_grp_cd;
SELECT count(*) AS total_codes, count(*) FILTER (WHERE use_yn = 'Y') AS active
  FROM tc_common_code;

\echo '=== V-06  TH 가 파티션 테이블 (기대 p) ==='
SELECT relkind FROM pg_class WHERE relname = 'th_crawl_target';

\echo '=== V-07  TH 파티션 목록과 경계 (조회 가능 범위) ==='
SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) AS bounds
  FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid
 WHERE i.inhparent = 'th_crawl_target'::regclass
 ORDER BY c.relname;

\echo '=== V-08  CHECK 제약 존재 (기대 7행, 각 conrelid 지정) ==='
-- 파티션은 부모의 CHECK 제약을 복제하므로 conname 만으로 세면 부풀려진다.
-- 반드시 대상 테이블(conrelid)을 함께 지정한다.
SELECT conrelid::regclass AS tbl, conname
  FROM pg_constraint
 WHERE contype = 'c'
   AND (   (conrelid = 'tn_crawl_target'::regclass
            AND conname IN ('ck_crawl_target_site_binding','ck_crawl_target_direct_kind',
                            'ck_crawl_target_run_exclusion','ck_crawl_target_diag'))
        OR (conrelid = 'tn_collect_site_policy'::regclass
            AND conname IN ('ck_collect_site_policy','ck_collect_site_version'))
        OR (conrelid = 'th_crawl_target'::regclass
            AND conname = 'ck_h_crawl_target_diag'))
 ORDER BY 1, 2;

\echo '=== V-09  TW_AUDIT_LOG 에 UPDATE/DELETE 권한이 없어야 함 (기대 0행) ==='
SELECT grantee, privilege_type
  FROM information_schema.table_privileges
 WHERE table_name = 'tw_audit_log'
   AND grantee = 'lifelaw_web_app'
   AND privilege_type IN ('UPDATE','DELETE');

\echo '=== V-10  TN_CRAWL_TARGET UPDATE 권한이 allowlist 4개로 한정 ==='
SELECT column_name
  FROM information_schema.column_privileges
 WHERE table_name = 'tn_crawl_target'
   AND grantee = 'lifelaw_web_app'
   AND privilege_type = 'UPDATE'
 ORDER BY column_name;

\echo '=== V-10b  금지 컬럼에 UPDATE 권한이 없어야 함 (기대 0행) ==='
SELECT column_name
  FROM information_schema.column_privileges
 WHERE table_name = 'tn_crawl_target'
   AND grantee = 'lifelaw_web_app'
   AND privilege_type = 'UPDATE'
   AND column_name IN ('crawl_stat_cd','extract_stat_cd','norm_stat_cd','cmpr_stat_cd',
                       'change_yn_cd','raw_html_hash','norm_html_hash','prev_raw_hash',
                       'prev_norm_hash','crawl_diag_cd','crawl_diag_msg',
                       'crawl_candidate_url','file_size','file_mtime','file_format_cd',
                       'extract_method_cd','batch_ymd','run_collect_policy_cd',
                       'run_exclusion_site_policy_id','run_exclusion_site_policy_version',
                       'site_policy_id','site_collect_policy_cd','site_policy_version',
                       'effective_collect_policy_cd','execution_collect_policy_cd');

\echo '=== V-11  마이그레이션 적용 원장 ==='
SELECT version, filename, checksum, applied_by FROM tw_schema_migration ORDER BY version;

\echo '=== 보강  수집기 소유 테이블의 소유자가 Web 롤이 아님을 확인 ==='
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
   AND c.relname NOT LIKE 'tw\_%'
 ORDER BY c.relname;

\echo '=== 보강  RBAC seed (기대 role=6 perm=14 role_perm=35) ==='
SELECT (SELECT count(*) FROM tw_role) AS roles,
       (SELECT count(*) FROM tw_permission) AS perms,
       (SELECT count(*) FROM tw_role_permission) AS role_perms;

\echo '=== 보강  미부여 권한 (A-08 / 화면 미정 사유) ==='
SELECT perm_cd FROM tw_permission
 WHERE perm_cd NOT IN (SELECT perm_cd FROM tw_role_permission) ORDER BY perm_cd;

\echo '=== 보강  ADMIN 이 command:approve 를 갖지 않음 (4-eyes, 기대 0행) ==='
SELECT role_cd, perm_cd FROM tw_role_permission
 WHERE role_cd = 'ADMIN' AND perm_cd = 'command:approve';
