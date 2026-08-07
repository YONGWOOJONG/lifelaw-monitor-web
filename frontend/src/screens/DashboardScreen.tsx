/**
 * S-03 운영 현황 대시보드.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-03
 *
 * **`5001`(기준선 설정)을 변경 감지 건수에 합산하지 않는다.** 서버가 이미
 * `change_detected_cnt` 와 `baseline_cnt` 를 분리해 내려주므로, 화면에서 둘을
 * 더하지 않는다. 합산하면 신규 대상이 대량 등록된 날 변경이 폭증한 것처럼 보인다.
 *
 * **화면에는 코드값이 아니라 명칭을 보여준다.** 운영자가 `1090`·`5030` 을 외우고
 * 있을 이유가 없다. 라벨의 출처는 `TC_COMMON_CODE`(`useCodes().label`) 하나뿐이며
 * 한글을 이 파일에 하드코딩하지 않는다. 코드값은 툴팁에 남겨 두어, 계약 코드를
 * 확인해야 할 때 볼 수 있게 한다.
 *
 * 이 파일이 코드값을 직접 아는 곳은 모두 계약에서 온 상수다: 변경 판정 집합
 * (`CHANGE_CODES`), 기준선·상세변경·수집제외 코드, 그리고 아래 색조 표들.
 * 그 밖의 모든 한글은 `label()` 을 거친다.
 *
 * 색조는 **코드 그룹마다 다르게** 정한다.
 *   - 단계 상태(1xxx~4xxx): 끝 두 자리 규칙. 이 그룹들은 `00`·`10`·`20`·`90`
 *     네 접미만 쓰므로 규칙이 안정적이다.
 *   - `CHANGE_YN`·`RUN_STAT`: **명시 표.** 접미 규칙을 쓰면 뜻이 뒤집힌다.
 *     각 표 위 주석에 실제로 어떻게 틀렸는지 적어뒀다.
 *
 * 하나의 규칙으로 전부 덮으려 한 것이 원래 설계였고, 그게 이 화면에서 색이
 * 틀리는 유일한 원인이었다. 그룹을 나누는 쪽이 맞다.
 *
 * `change_trend` 는 `target:history:read` 가 없으면 서버가 내려주지 않는다. 그 경우
 * 추이 카드를 통째로 건너뛴다 — 0 으로 채운 가짜 막대를 그리지 않는다.
 */

import { useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import type { Dashboard } from '../api/types'
import { useAppBar } from '../app/AppBarContext'
import { useCodes } from '../app/CodeContext'
import { Link } from '../app/router'
import { CodeLabel, ErrorBanner, Loading, formatInstant, formatYmd } from '../components/common'

/** 변경으로 세는 판정 코드. 계약 상수이며 `5001`(기준선)은 포함하지 않는다. */
const CHANGE_CODES = new Set(['5020', '5040'])
const BASELINE_CODE = '5001'
/** 상세내용 변경됨. 알림 카드가 이 코드 하나만 걸러 보여준다. */
const DETAIL_CHANGED_CODE = '5040'
/** 실행 정책 "수집 제외". `excluded_cnt` 를 세는 기준과 같은 코드다. */
const EXCLUDED_POLICY_CODE = '7020'

/**
 * 막대 세그먼트에 쓸 수 있는 색조. **CSS 에 `.seg-*` 가 실재하는 값만 있다.**
 * 없는 이름이 나오면 배경 없는 투명한 구멍이 되므로 타입으로 막는다.
 */
type SegTone = 'ok' | 'fail' | 'wait' | 'none' | 'idle' | 'baseline' | 'change' | 'change-detail'

/** 실행 상태 점에 쓸 색조. `.dot-*` 가 실재하는 값만 있다. */
type DotTone = 'ok' | 'fail' | 'wait' | 'none' | 'idle' | 'run' | 'warn' | 'change'

/**
 * 단계 상태(수집·추출·정규화·비교)의 색조. 끝 두 자리 규칙이 **여기서만** 맞다.
 *
 * 이 네 그룹의 계약 코드는 `00` 비대상 · `10` 대기 · `20` 성공 · `90` 실패 뿐이며
 * `30`·`40` 은 아예 쓰이지 않는다. 그래서 규칙이 안정적이다 — 같은 단계에 코드가
 * 늘어도 접미가 뜻을 유지한다.
 *
 * 모르는 접미는 `idle` 로 떨어뜨린다. **없는 CSS 클래스로 떨어지면 안 된다.**
 */
function stageTone(code: string): SegTone {
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
 *   - `5030`(상세내용 변경없음) → `30` → 'run' → `.seg-run` 이 CSS 에 없어
 *     막대에 투명한 구멍이 났다. 시드에 8건 있어 눈에 바로 보였다.
 *   - `5010`(변경없음) → `10` → 'wait' → 아무도 기다리지 않는데 "대기" 회색.
 *
 * 그래서 명시 표로 둔다. 표의 길이가 6줄이라는 게 규칙보다 나은 이유다 —
 * 코드가 늘면 여기서 실패하고, 규칙이면 조용히 틀린 색을 쓴다.
 *
 * `5020` 원본 변경과 `5040` 상세 변경은 **다른 색**이다(2a 시안). 둘을 같은
 * 파랑으로 묶으면 "무엇이 바뀌었나"가 막대에서 사라진다.
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
 * **둘이 서로 뒤바뀌어** 있었다. 돌고 있는 배치가 완료처럼, 끝난 배치가 진행
 * 중처럼 보였다.
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
const RUN_IN_PROGRESS: ReadonlySet<string> = new Set(['6010', '6020'])

function changeTone(code: string): SegTone {
  return CHANGE_TONE[code] ?? 'idle'
}

function runTone(code: string): DotTone {
  return RUN_TONE[code] ?? 'idle'
}

function sum(counts: Record<string, number>): number {
  return Object.values(counts).reduce((acc, n) => acc + n, 0)
}

function sorted(counts: Record<string, number>): [string, number][] {
  return Object.entries(counts)
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => a.localeCompare(b))
}

function pct(value: number, total: number): string {
  return total > 0 ? `${(value / total) * 100}%` : '0%'
}

/** `.seg` 의 padding-left(7px) + 오른쪽 여유. */
const SEG_PADDING_PX = 11

/**
 * 글자의 렌더 폭(px) 어림. 한글은 글꼴 크기만큼, 그 밖(숫자·라틴·공백)은 그 절반쯤.
 *
 * **비율이 아니라 px 로 재는 이유:** 이전 판은 "막대 전체의 몇 할"로 판단했는데,
 * 같은 비율이라도 창이 좁으면 실제 px 가 줄어든다. 1600px 에서 맞춘 계수가
 * 1280px 에서 두 칸을 잘라냈다(실측). 칸의 실제 px 를 기준으로 삼으면 창 폭과
 * 무관하게 판단이 맞는다.
 */
function textWidthPx(text: string, fontPx: number): number {
  let width = 0
  for (const ch of text) width += /[ᄀ-ᇿ㄰-㆏가-힣]/.test(ch) ? fontPx : fontPx * 0.55
  return width
}

/**
 * 세그먼트에 넣을 글자. **폭에 따라 세 단계로 물러난다.**
 *
 *   이름 + 건수  →  건수만  →  색만
 *
 * 가운데 단계가 있는 이유: 8건짜리 칸은 폭이 7% 뿐인데 이름이 "상세내용
 * 변경없음" 처럼 길면 어떤 식으로도 안 들어간다. 그렇다고 통째로 비우면 아무
 * 내용 없는 칸이 남는다 — 건수만이라도 보이는 쪽이 낫다. 잘라서 보여주지는
 * 않는다(그래도 넘치면 CSS 가 `…` 로 처리한다).
 */
function segText(name: string, count: number, availablePx: number, fontPx = 10.5): string | null {
  const amount = count.toLocaleString('ko-KR')
  const room = availablePx - SEG_PADDING_PX
  const full = `${name} ${amount}`
  if (textWidthPx(full, fontPx) <= room) return full
  if (textWidthPx(amount, fontPx) <= room) return amount
  return null
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: 'muted' | 'warn' }) {
  return (
    <div>
      <div className="metric-label">{label}</div>
      <div className={tone ? `metric-value is-${tone}` : 'metric-value'}>
        {value.toLocaleString('ko-KR')}
      </div>
    </div>
  )
}

/**
 * 단계별 누적 막대 한 줄. 세그먼트에는 **명칭 + 건수**를, 툴팁에는 코드값까지 둔다.
 *
 * 색조 함수를 **호출부가 넘긴다.** 막대 안에서 코드값을 보고 그룹을 추측하면
 * (`5`로 시작하면 변경 판정…) 그 추측이 또 하나의 규칙이 되고, 규칙이 틀리는
 * 것이 애초의 문제였다. 어느 그룹을 그리는지는 호출부가 이미 알고 있다.
 */
function StageBar({
  name,
  counts,
  tone,
  summary,
}: {
  name: string
  counts: Record<string, number>
  tone: (code: string) => SegTone
  summary?: boolean
}) {
  const { label } = useCodes()
  // 막대의 실제 px 폭. 창 크기가 바뀌면 다시 재고 표기를 다시 고른다.
  // 첫 렌더에는 0 이므로 그때는 색만 나오고, 관찰자가 값을 채우면 글자가 붙는다.
  const stackRef = useRef<HTMLDivElement>(null)
  const [stackPx, setStackPx] = useState(0)

  useEffect(() => {
    const node = stackRef.current
    if (!node) return
    const observer = new ResizeObserver((entries_) => {
      setStackPx(entries_[0]?.contentRect.width ?? 0)
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const entries = sorted(counts)
  const total = sum(counts)
  if (total === 0) return null

  return (
    <div className={summary ? 'dist-row is-summary' : 'dist-row'}>
      <div className="dist-name">{name}</div>
      <div className="stack" ref={stackRef}>
        {entries.map(([code, count]) => {
          const width = pct(count, total)
          // 이름 → 건수 → 색만. 칸의 실제 px 에 맞는 가장 긴 표기를 고른다.
          const text = segText(label(code), count, (count / total) * stackPx)
          return (
            <div
              key={code}
              className={`seg seg-${tone(code)}`}
              style={{ width }}
              // 툴팁에는 코드값까지 넣는다. 화면에서 이름만 보이더라도 계약
              // 코드를 확인해야 하는 순간이 있다.
              title={`${code} ${label(code)} · ${count.toLocaleString('ko-KR')}건`}
            >
              {text}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Trend({
  points,
  today,
}: {
  points: NonNullable<Dashboard['change_trend']>
  /** 대상이 하나도 없으면 서버가 `null` 을 준다. 그 경우 오늘로 표시할 열이 없다. */
  today: string | null
}) {
  const { label } = useCodes()
  const peak = Math.max(...points.map((p) => p.change_detected_cnt), 1)
  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">변경 감지 추이</div>
        <div className="card-note">
          최근 {points.length} 업무일 · 막대 ={' '}
          {[...CHANGE_CODES]
            .sort()
            .map((code) => label(code))
            .join(' + ')}
        </div>
      </div>
      <div className="trend">
        {points.map((point) => {
          // 오늘 강조가 실패 표시보다 우선한다. 오늘이면서 실패인 날은 "진행 중
          // 이라 아직 낮다"가 먼저 읽혀야 한다.
          const state = point.batch_ymd === today ? ' is-today' : point.failed ? ' is-fail' : ''
          return (
            <div
              key={point.batch_ymd}
              className={`trend-col${state}`}
              title={
                `${formatYmd(point.batch_ymd)} · ${point.change_detected_cnt.toLocaleString('ko-KR')}건` +
                (point.failed ? ' · 배치 실패' : '')
              }
            >
              <div className="trend-slot">
                <div
                  className="trend-bar"
                  style={{ height: `${(point.change_detected_cnt / peak) * 100}%` }}
                />
              </div>
              <div className="trend-tick">{formatYmd(point.batch_ymd).slice(5)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Alert({
  to,
  tone,
  count,
  title,
  detail,
}: {
  to: string
  tone: 'fail' | 'change' | 'warn' | 'idle'
  count: number
  title: string
  detail: string
}) {
  return (
    <Link to={to} className={`alert alert-${tone}`}>
      <div className={`alert-count is-${tone}`}>{count.toLocaleString('ko-KR')}</div>
      <div className="alert-body">
        <div className="alert-title">{title}</div>
        <div className="alert-detail">{detail}</div>
      </div>
      <div className="alert-link">목록 →</div>
    </Link>
  )
}

/**
 * 실행 소요 시간. **끝난 실행에만 쓴다** — 진행 중 판단은 호출부가
 * `RUN_IN_PROGRESS` 로 먼저 한다.
 *
 * 그래서 `ended_at` 이 비면 '진행 중' 이 아니라 `—` 다. 상태가 이미 종료인데
 * 종료 시각이 없는 실행(죽은 실행)을 "진행 중"으로 부르면 안 된다.
 */
function duration(startedAt: string | null, endedAt: string | null): string {
  if (!startedAt || !endedAt) return '—'
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime()
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const minutes = Math.round(ms / 60000)
  return minutes < 60 ? `${minutes}분` : `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`
}

export function DashboardScreen() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<unknown>(null)
  // 코드값 대신 명칭을 보여준다. 라벨의 출처는 `TC_COMMON_CODE` 하나뿐이며
  // 여기서 한글을 하드코딩하지 않는다. 코드를 못 찾으면 `label` 이 코드값을
  // 그대로 돌려주므로 화면이 비지 않는다.
  const { label } = useCodes()

  useEffect(() => {
    void api.get<Dashboard>('/api/dashboard').then(setData).catch(setError)
  }, [])

  // `run_stat_cd` 로 판단한다. `ended_at` 이 비었는지로 보면 종료 시각을 쓰지
  // 못하고 죽은 실행이 앱바에 영원히 "진행 중"으로 남는다.
  const running = data?.latest_runs.find((run) => RUN_IN_PROGRESS.has(run.run_stat_cd))

  // 업무일자와 진행 중인 배치는 앱바가 갖는다. 어느 화면에 있든 같은 자리에 보인다.
  useAppBar(
    data ? (
      <>
        <span className="stamp">batch_ymd {data.batch_ymd ?? '—'}</span>
        {running ? (
          <Link to={`/batch-runs/${running.run_id}`} className="running">
            실행 #{running.run_id} <CodeLabel value={running.run_stat_cd} />
          </Link>
        ) : null}
      </>
    ) : null,
    [data?.batch_ymd, running?.run_id, running?.run_stat_cd],
  )

  if (error) return <ErrorBanner error={error} />
  if (!data) return <Loading what="운영 현황을" />

  const changeCodes = sorted(data.change_yn)
    .filter(([code]) => CHANGE_CODES.has(code))
    .map(([code, count]) => `${label(code)} ${count}`)
    .join(' + ')
  // **네 단계를 모두 센다.** `norm_stat` 을 빼면 3090 이 생겼을 때 큰 숫자
  // (`failed_cnt`)에는 들어가는데 아래 코드 목록과 실패 카드 설명에는 안 나온다.
  // 같은 화면에서 두 숫자가 어긋나는 종류의 버그다.
  const failCodes = [data.crawl_stat, data.extract_stat, data.norm_stat, data.cmpr_stat]
    .flatMap((counts) => sorted(counts))
    .filter(([code]) => stageTone(code) === 'fail')
    .map(([code, count]) => `${label(code)} ${count}`)
    .join(' · ')
  const detailChanged = data.change_yn[DETAIL_CHANGED_CODE] ?? 0

  return (
    <div className="dash">
      <div className="dash-top">
        <div className="card">
          <div className="card-note" style={{ marginBottom: 14 }}>
            오늘 지표
          </div>

          <div className="headline">
            <div className="headline-value is-change">
              {data.change_detected_cnt.toLocaleString('ko-KR')}
            </div>
            <div className="headline-label">변경 감지</div>
          </div>
          <div className="headline-sub">
            {changeCodes || '—'} · {label(BASELINE_CODE)} 제외
          </div>

          <div className="headline">
            <div className="headline-value is-fail">{data.failed_cnt.toLocaleString('ko-KR')}</div>
            <div className="headline-label">실패</div>
          </div>
          <div className="headline-sub">{failCodes || '—'}</div>

          <div className="metric-grid">
            <Metric label="전체 대상" value={data.total_targets} />
            {/* 지표 이름도 코드 명칭에서 가져온다. "기준선 5001" 처럼 숫자를
                붙여 부르면 이 화면만 아는 이름이 하나 더 생긴다. */}
            <Metric label={label(BASELINE_CODE)} value={data.baseline_cnt} tone="muted" />
            <Metric label={label(EXCLUDED_POLICY_CODE)} value={data.excluded_cnt} />
            <Metric label="진단 대상" value={data.diagnostic_cnt} tone="warn" />
          </div>
        </div>

        <div className="dash-col">
          {data.change_trend?.length ? (
            <Trend points={data.change_trend} today={data.batch_ymd} />
          ) : null}

          <div className="card">
            <div className="card-head">
              <div className="card-title">단계별 분포</div>
            </div>
            <StageBar name="수집" counts={data.crawl_stat} tone={stageTone} />
            <StageBar name="추출" counts={data.extract_stat} tone={stageTone} />
            <StageBar name="정규화" counts={data.norm_stat} tone={stageTone} />
            <StageBar name="비교" counts={data.cmpr_stat} tone={stageTone} />
            {/* 변경 판정만 다른 표를 쓴다. 접미 규칙이 이 그룹에서 뜻을 뒤집는다. */}
            <StageBar name="변경 판정" counts={data.change_yn} tone={changeTone} summary />
          </div>
        </div>
      </div>

      <div className="dash-bottom">
        <div className="stack-col">
          <div className="section-head">
            <div className="section-title">확인이 필요한 것</div>
            <Link to="/targets" className="section-link">
              수집 대상 전체 →
            </Link>
          </div>
          <div className="alerts">
            <Alert
              to="/targets?crawl_stat_cd=1090"
              tone="fail"
              count={data.failed_cnt}
              title="수집 실패"
              detail={failCodes || '실패 코드 없음'}
            />
            {/* 카드 제목도 코드 명칭을 쓴다. 설명문은 코드 라벨이 아니라 이
                화면의 안내 문구이므로 그대로 둔다 — 하드코딩 금지 규칙은
                코드 라벨에 대한 것이다. */}
            <Alert
              to={`/targets?change_yn_cd=${DETAIL_CHANGED_CODE}`}
              tone="change"
              count={detailChanged}
              title={label(DETAIL_CHANGED_CODE)}
              detail="diff 생성됨 · 검토 대기"
            />
            <Alert
              to="/targets?has_diagnostic=true"
              tone="warn"
              count={data.diagnostic_cnt}
              title="진단 대상"
              detail="표시만 하며 자동 교체하지 않음"
            />
            <Alert
              to={`/targets?execution_collect_policy_cd=${EXCLUDED_POLICY_CODE}`}
              tone="idle"
              count={data.excluded_cnt}
              title={label(EXCLUDED_POLICY_CODE)}
              detail="실행 정책 기준 · 사이트 정책 상속 포함"
            />
          </div>
        </div>

        <div className="stack-col">
          <div className="section-head">
            <div className="section-title">최근 배치 실행</div>
            <Link to="/batch-runs" className="section-link">
              전체 →
            </Link>
          </div>
          <div className="runs">
            {data.latest_runs.map((run) => (
              <Link key={run.run_id} to={`/batch-runs/${run.run_id}`} className="row">
                <span className={`dot dot-${runTone(run.run_stat_cd)}`} />
                <div className="row-body">
                  <div className="row-date">{formatYmd(run.batch_ymd)}</div>
                  <div className="row-sub">
                    {run.run_mode} · <CodeLabel value={run.run_stat_cd} /> ·{' '}
                    {RUN_IN_PROGRESS.has(run.run_stat_cd)
                      ? formatInstant(run.started_at)
                      : duration(run.started_at, run.ended_at)}
                  </div>
                </div>
                <div className="row-figs">
                  <div className="a">{run.change_detected_cnt.toLocaleString('ko-KR')} 변경</div>
                  {/* 2a 원안대로 "실패"를 쓴다. 대상 수는 어느 날이나 거의 같아서
                      한 줄을 쓸 값이 못 되고, 실패 건수는 날마다 다르다. */}
                  <div className="b">{run.fail_cnt.toLocaleString('ko-KR')} 실패</div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
