/**
 * API 응답 타입.
 *
 * 권위: docs/contracts/db-contract.md (컬럼 계약의 단일 출처)
 *
 * 행 스키마를 여기서 전부 다시 선언하지 않는다. 계약 문서와 이중 정의가 되면
 * C-1 과 같은 드리프트가 생긴다. 화면이 실제로 읽는 필드만 좁게 선언하고,
 * 나머지는 인덱스 시그니처로 통과시킨다.
 */

export interface Principal {
  user_id: number
  login_id: string
  user_nm: string
  roles: string[]
  /**
   * 메뉴 표시용이다. **인가가 아니다.**
   * 설계 §17.3 — 프론트엔드의 메뉴 숨김은 인가가 아니며 서버가 매 요청 검증한다.
   */
  permissions: string[]
  /**
   * 세션에서 유도된 CSRF 토큰. `/api/auth/me` 가 함께 내려주므로 **새로고침
   * 뒤에도 복구된다.** 이 값이 없으면 상태 변경 요청이 전부 CSRF_FAILED 로
   * 막히고, 재인증도 POST 라 회복 경로가 없다.
   */
  csrf_token: string
  session: {
    absolute_expires_at: string
    reauth_fresh: boolean
  }
}

export interface LoginResponse {
  principal: Principal
  csrf_token: string
}

export interface PageEnvelope<T> {
  items: T[]
  limit: number
  offset: number
  has_more: boolean
}

export interface CountResponse {
  count: number
}

export type Row = Record<string, unknown>

export interface TargetRow extends Row {
  url_id: number
  con_link_seq: number
  con_link_url: string
  link_class_cd: string
  collect_target_kind_cd: string | null
  site_host: string | null
  site_collect_policy_cd: string
  target_collect_policy_cd: string
  /** 구성 정책 = site OR target. 계산 컬럼이므로 표시만 한다. */
  effective_collect_policy_cd: string
  /** 실행 정책 = site OR target OR run. `effective` 와 혼용하지 않는다. */
  execution_collect_policy_cd: string
  run_collect_policy_cd: string
  /** S-09 일괄 변경의 낙관적 잠금 입력. */
  target_policy_version: number
  batch_ymd: string
  crawl_stat_cd: string
  extract_stat_cd: string
  norm_stat_cd: string
  cmpr_stat_cd: string
  change_yn_cd: string
  crawl_diag_cd: string | null
}

export interface HistoryPage extends PageEnvelope<Row> {
  /** 실제 파티션에서 도출한 조회 가능 업무월. 범위 밖의 0건은 유실이 아니다. */
  available_months: string[]
  min_batch_ymd: string | null
  max_batch_ymd: string | null
}

export interface BatchRunRow extends Row {
  run_id: number
  batch_ymd: string
  run_mode: string
  run_stat_cd: string
  started_at: string | null
  ended_at: string | null
  total_cnt: number
  success_cnt: number
  fail_cnt: number
  change_detected_cnt: number
  err_cnt: number
  excluded_cnt: number
}

export interface CommonCode {
  code_grp_cd: string
  code_val: string
  code_nm: string
  code_const: string | null
  sort_ord: number
}

export interface SitePolicy extends Row {
  site_policy_id: number
  site_host: string
  collect_policy_cd: string
  policy_version: number
  policy_reason: string | null
  target_cnt: number
}

export interface Dashboard {
  batch_ymd: string | null
  total_targets: number
  crawl_stat: Record<string, number>
  extract_stat: Record<string, number>
  norm_stat: Record<string, number>
  cmpr_stat: Record<string, number>
  change_yn: Record<string, number>
  /** 5020 + 5040. **5001 은 포함되지 않는다.** */
  change_detected_cnt: number
  /** 5001 기준선 설정. 변경 감지와 별개 지표다. */
  baseline_cnt: number
  failed_cnt: number
  excluded_cnt: number
  diagnostic_cnt: number
  latest_runs: BatchRunRow[]
  /**
   * 최근 업무일별 변경 감지 추이(최대 14 업무일).
   *
   * 이력 표에서 나오므로 `target:history:read` 가 없으면 **필드 자체가 없다.**
   * 없는 것(권한 없음)과 빈 배열(조회 범위에 자료 없음)은 다르지만, 화면은
   * 둘 다 카드를 그리지 않는 것으로 같게 처리한다 — 가짜 막대를 그리지 않는다.
   */
  change_trend?: { batch_ymd: string; change_detected_cnt: number; failed: boolean }[]
}

export interface ContractCheck {
  check_id: string
  title: string
  ok: boolean
  informational: boolean
  detail: string
}

export interface ContractStatus {
  pin: {
    c1_version: string
    g1_version: string
    ddl_filename: string
    expected_migration: string
  }
  all_passed: boolean
  failed_count: number
  checks: ContractCheck[]
}
