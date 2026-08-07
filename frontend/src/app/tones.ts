/**
 * 코드값 → 색조.
 *
 * 권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md 부록(공개 계약 코드 요약)
 *       코드 명칭의 단일 출처는 `TC_COMMON_CODE` 다. 이 파일은 코드 → **색조**만 정한다.
 *
 * 이 표는 **화면마다 복제하지 않는다.** 운영 현황과 수집 대상이 같은 코드를
 * 다른 색으로 그리면, 두 화면을 오가는 운영자가 색을 신뢰할 수 없게 된다.
 * 원래 DashboardScreen 안에 있던 것을 그대로 옮겨왔다.
 *
 * 색조는 코드 그룹마다 다르게 정한다.
 *   - 단계 상태(1xxx~4xxx): 끝 두 자리 규칙. 이 그룹들은 `00`·`10`·`20`·`90`
 *     네 접미만 쓰므로 규칙이 안정적이다.
 *   - CHANGE_YN·RUN_STAT: 명시 표. 접미 규칙을 쓰면 뜻이 뒤집힌다.
 *     각 표 위 주석에 실제로 어떻게 틀렸는지 적어뒀다.
 */

/** 변경으로 세는 판정 코드. 계약 상수이며 `5001`(기준선)은 포함하지 않는다. */
export const CHANGE_CODES = new Set(['5020', '5040'])
export const BASELINE_CODE = '5001'
/** 상세내용 변경됨. */
export const DETAIL_CHANGED_CODE = '5040'
/** 실행 정책 "수집 제외". `excluded_cnt` 를 세는 기준과 같은 코드다. */
export const EXCLUDED_POLICY_CODE = '7020'

/**
 * 막대 세그먼트와 단계 셀에 쓸 수 있는 색조. **CSS 에 `.seg-*` / `.stage-*` 가
 * 실재하는 값만 있다.** 없는 이름이 나오면 배경 없는 투명한 구멍이 되므로
 * 타입으로 막는다.
 */
export type SegTone = 'ok' | 'fail' | 'wait' | 'none' | 'idle' | 'baseline' | 'change' | 'change-detail'

/** 실행 상태 점에 쓸 색조. `.dot-*` 가 실재하는 값만 있다. */
export type DotTone = 'ok' | 'fail' | 'wait' | 'none' | 'idle' | 'run' | 'warn' | 'change'

/**
 * 단계 상태(수집·추출·정규화·비교)의 색조. 끝 두 자리 규칙이 **여기서만** 맞다.
 *
 * 이 네 그룹의 계약 코드는 `00` 비대상 · `10` 대기 · `20` 성공 · `90` 실패 뿐이며
 * `30`·`40` 은 아예 쓰이지 않는다. 그래서 규칙이 안정적이다.
 *
 * 모르는 접미는 `idle` 로 떨어뜨린다. **없는 CSS 클래스로 떨어지면 안 된다.**
 */
export function stageTone(code: string): SegTone {
  switch (code.slice(-2)) {
    case '90':
      return 'fail'
    case '20':
      return 'ok'
    case '10':
      return 'wait'
    case '00':
      return 'none'
    default:
      return 'idle'
  }
}

/**
 * 변경 판정(CHANGE_YN)의 색조. **접미 규칙을 쓰지 않는다.**
 *
 * 접미 규칙을 이 그룹에 적용하면 뜻이 뒤집힌다. 실측으로 확인한 것:
 *   - `5030`(상세내용 변경없음) → `30` → 'run' → CSS 에 없는 클래스라 투명한 구멍
 *   - `5010`(변경없음) → `10` → 'wait' → 아무도 기다리지 않는데 "대기" 회색
 *
 * `5020` 원본 변경과 `5040` 상세 변경은 **다른 색**이다(2a 시안).
 */
const CHANGE_TONE: Readonly<Record<string, SegTone>> = {
  '5000': 'none', // 본문 변경 미확인 — 아직 판정 전
  '5001': 'baseline', // 기준선 설정 — 변경 감지와 별개 지표
  '5010': 'ok', // 변경없음 — 정상 결과다
  '5020': 'change', // 원본 변경
  '5030': 'ok', // 상세내용 변경없음 — 역시 정상 결과다
  '5040': 'change-detail', // 상세내용 변경됨
}

/**
 * 실행 상태(RUN_STAT)의 색조. 이것도 접미 규칙이 맞지 않는다.
 *
 * `6020`(실행 중) → `20` → 'ok' 초록, `6030`(정상 종료) → `30` → 'run' 파랑으로
 * **둘이 서로 뒤바뀌어** 있었다.
 */
const RUN_TONE: Readonly<Record<string, DotTone>> = {
  '6010': 'wait', // 실행 대기
  '6020': 'run', // 실행 중
  '6030': 'ok', // 정상 종료
  '6040': 'warn', // 부분 성공
  '6080': 'idle', // 취소
  '6090': 'fail', // 실패/중단
}

/**
 * 아직 끝나지 않은 실행. **`ended_at` 이 비었는지로 판단하지 않는다.**
 *
 * `ended_at` 을 쓰지 못하고 죽은 실행은 영원히 "진행 중"으로 남는다. 실행
 * 상태의 권위 있는 값은 `run_stat_cd` 이고, 그 최종 작성자는 수집기다.
 */
export const RUN_IN_PROGRESS: ReadonlySet<string> = new Set(['6010', '6020'])

export function changeTone(code: string): SegTone {
  return CHANGE_TONE[code] ?? 'idle'
}

export function runTone(code: string): DotTone {
  return RUN_TONE[code] ?? 'idle'
}
