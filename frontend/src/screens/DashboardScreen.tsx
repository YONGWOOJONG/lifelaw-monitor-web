/**
 * S-03 운영 현황 대시보드.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-03
 *
 * **`5001`(기준선 설정)을 변경 감지 건수에 합산하지 않는다.** 서버가 이미
 * `change_detected_cnt` 와 `baseline_cnt` 를 분리해 내려주므로, 화면에서 둘을
 * 더하지 않는다. 합산하면 신규 대상이 대량 등록된 날 변경이 폭증한 것처럼 보인다.
 *
 * **한글 라벨을 하드코딩하지 않는다.** 코드 라벨은 `CodeLabel`(=`TC_COMMON_CODE`)
 * 이 유일한 출처다. 이 파일이 코드값을 직접 아는 곳은 두 군데뿐이며 둘 다 계약에서
 * 온 상수다: 변경 판정 코드 집합(`CHANGE_CODES`)과 색조를 정하는 접미 두 자리 규칙.
 *
 * 색조 규칙(`toneOf`): 코드값 끝 두 자리가 계약상 단계 결과를 뜻한다.
 *   `00` 비대상 · `10` 대기 · `20`·`40` 성공/완료 · `30` 진행중 · `90` 실패
 * 코드가 늘어나도 매핑 표를 고칠 필요가 없도록 값을 열거하지 않고 규칙으로 쓴다.
 *
 * 서버에 아직 없는 것:
 *   - `change_trend` (최근 업무일별 변경 감지 추이). 내려오면 추이 카드를 그리고,
 *     없으면 그 카드를 통째로 건너뛴다. 가짜 데이터를 그리지 않는다.
 *   - `norm_stat` (정규화 단계 분포). 마찬가지로 있으면 한 줄 늘어난다.
 */

import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { Dashboard } from '../api/types'
import { useAppBar } from '../app/AppBarContext'
import { Link } from '../app/router'
import { CodeLabel, ErrorBanner, Loading, formatInstant, formatYmd } from '../components/common'

/** 변경으로 세는 판정 코드. 계약 상수이며 `5001`(기준선)은 포함하지 않는다. */
const CHANGE_CODES = new Set(['5020', '5040'])
const BASELINE_CODE = '5001'

type Tone = 'ok' | 'fail' | 'wait' | 'none' | 'run' | 'idle'

/** 코드값 끝 두 자리로 색조를 정한다. 위 주석의 규칙 참조. */
function toneOf(code: string): Tone {
  switch (code.slice(-2)) {
    case '90':
      return 'fail'
    case '20':
    case '40':
      return 'ok'
    case '30':
      return 'run'
    case '10':
      return 'wait'
    case '00':
      return 'none'
    default:
      return 'idle'
  }
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

/** 단계별 누적 막대 한 줄. 세그먼트 라벨은 코드값 + 건수로, 이름은 툴팁에 둔다. */
function StageBar({
  name,
  counts,
  summary,
}: {
  name: string
  counts: Record<string, number>
  summary?: boolean
}) {
  const entries = sorted(counts)
  const total = sum(counts)
  if (total === 0) return null

  return (
    <div className={summary ? 'dist-row is-summary' : 'dist-row'}>
      <div className="dist-name">{name}</div>
      <div className="stack">
        {entries.map(([code, count]) => {
          const tone = code === BASELINE_CODE ? 'baseline' : CHANGE_CODES.has(code) ? 'change' : toneOf(code)
          const width = pct(count, total)
          // 좁은 세그먼트는 글자를 빼고 색만 남긴다. 잘린 숫자가 더 나쁘다.
          const wide = count / total > 0.09
          return (
            <div
              key={code}
              className={`seg seg-${tone}`}
              style={{ width }}
              title={`${code} ${count.toLocaleString('ko-KR')}건`}
            >
              {wide ? `${code} · ${count.toLocaleString('ko-KR')}` : null}
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
  const peak = Math.max(...points.map((p) => p.change_detected_cnt), 1)
  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">변경 감지 추이</div>
        <div className="card-note">
          최근 {points.length} 업무일 · 막대 = {[...CHANGE_CODES].sort().join('+')}
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

function duration(startedAt: string | null, endedAt: string | null): string {
  if (!startedAt) return '—'
  if (!endedAt) return '진행 중'
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime()
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const minutes = Math.round(ms / 60000)
  return minutes < 60 ? `${minutes}분` : `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`
}

export function DashboardScreen() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    void api.get<Dashboard>('/api/dashboard').then(setData).catch(setError)
  }, [])

  const running = data?.latest_runs.find((run) => !run.ended_at)

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
    .map(([code, count]) => `${code} ${count}`)
    .join(' + ')
  const failCodes = [data.crawl_stat, data.extract_stat, data.cmpr_stat]
    .flatMap((counts) => sorted(counts))
    .filter(([code]) => toneOf(code) === 'fail')
    .map(([code, count]) => `${code} ${count}`)
    .join(' · ')
  const detailChanged = data.change_yn['5040'] ?? 0

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
            {changeCodes || '—'} · {BASELINE_CODE} 제외
          </div>

          <div className="headline">
            <div className="headline-value is-fail">{data.failed_cnt.toLocaleString('ko-KR')}</div>
            <div className="headline-label">실패</div>
          </div>
          <div className="headline-sub">{failCodes || '—'}</div>

          <div className="metric-grid">
            <Metric label="전체 대상" value={data.total_targets} />
            <Metric label={`기준선 ${BASELINE_CODE}`} value={data.baseline_cnt} tone="muted" />
            <Metric label="수집 제외" value={data.excluded_cnt} />
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
            <StageBar name="수집" counts={data.crawl_stat} />
            <StageBar name="추출" counts={data.extract_stat} />
            {data.norm_stat ? <StageBar name="정규화" counts={data.norm_stat} /> : null}
            <StageBar name="비교" counts={data.cmpr_stat} />
            <StageBar name="변경 판정" counts={data.change_yn} summary />
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
            <Alert
              to="/targets?change_yn=5040"
              tone="change"
              count={detailChanged}
              title="상세내용 변경됨"
              detail="5040 · diff 생성됨 · 검토 대기"
            />
            <Alert
              to="/targets?diagnostic=1"
              tone="warn"
              count={data.diagnostic_cnt}
              title="진단 대상"
              detail="표시만 하며 자동 교체하지 않음"
            />
            <Alert
              to="/targets?excluded=1"
              tone="idle"
              count={data.excluded_cnt}
              title="수집 제외"
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
                <span className={`dot dot-${toneOf(run.run_stat_cd)}`} />
                <div className="row-body">
                  <div className="row-date">{formatYmd(run.batch_ymd)}</div>
                  <div className="row-sub">
                    {run.run_mode} · <CodeLabel value={run.run_stat_cd} /> ·{' '}
                    {run.ended_at ? duration(run.started_at, run.ended_at) : formatInstant(run.started_at)}
                  </div>
                </div>
                <div className="row-figs">
                  <div className="a">{run.change_detected_cnt.toLocaleString('ko-KR')} 변경</div>
                  <div className="b">{run.total_cnt.toLocaleString('ko-KR')} 대상</div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
