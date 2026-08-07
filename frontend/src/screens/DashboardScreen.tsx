/**
 * S-03 운영 현황 대시보드.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-03
 *
 * **`5001`(기준선 설정)을 변경 감지 건수에 합산하지 않는다.** 서버가 이미
 * `change_detected_cnt` 와 `baseline_cnt` 를 분리해 내려주므로, 화면에서 둘을
 * 더하지 않는다. 합산하면 신규 대상이 대량 등록된 날 변경이 폭증한 것처럼 보인다.
 */

import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { Dashboard } from '../api/types'
import { Link } from '../app/router'
import { CodeLabel, ErrorBanner, Loading, formatInstant, formatYmd } from '../components/common'

function Tile({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value.toLocaleString('ko-KR')}</div>
      {hint ? <div className="tile-hint">{hint}</div> : null}
    </div>
  )
}

function Distribution({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort(([a], [b]) => a.localeCompare(b))
  return (
    <div className="panel">
      <h3>{title}</h3>
      <table className="grid">
        <tbody>
          {entries.map(([code, count]) => (
            <tr key={code}>
              <td>
                <CodeLabel value={code} />
              </td>
              <td className="num">{count.toLocaleString('ko-KR')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DashboardScreen() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    void api
      .get<Dashboard>('/api/dashboard')
      .then(setData)
      .catch(setError)
  }, [])

  if (error) return <ErrorBanner error={error} />
  if (!data) return <Loading what="운영 현황을" />

  return (
    <div className="screen">
      <h2>운영 현황</h2>
      <p className="muted">최신 업무일자 {formatYmd(data.batch_ymd)}</p>

      <div className="tiles">
        <Tile label="전체 대상" value={data.total_targets} />
        <Tile label="변경 감지" value={data.change_detected_cnt} hint="5020 원본 변경 + 5040 상세 변경" />
        <Tile label="기준선 설정" value={data.baseline_cnt} hint="5001 — 변경 감지에 포함하지 않음" />
        <Tile label="실패" value={data.failed_cnt} />
        <Tile label="수집 제외" value={data.excluded_cnt} hint="실행 정책 기준" />
        <Tile label="진단 대상" value={data.diagnostic_cnt} hint="HTTPS 전환·URL 이전 후보" />
      </div>

      <div className="panels">
        <Distribution title="수집 상태" counts={data.crawl_stat} />
        <Distribution title="변경 판정" counts={data.change_yn} />
        <Distribution title="추출 상태" counts={data.extract_stat} />
        <Distribution title="비교 상태" counts={data.cmpr_stat} />
      </div>

      <div className="panel">
        <h3>최근 배치 실행</h3>
        <table className="grid">
          <thead>
            <tr>
              <th>업무일자</th>
              <th>모드</th>
              <th>상태</th>
              <th className="num">대상</th>
              <th className="num">변경</th>
              <th>시작</th>
              <th>종료</th>
            </tr>
          </thead>
          <tbody>
            {data.latest_runs.map((run) => (
              <tr key={run.run_id}>
                <td>
                  <Link to={`/batch-runs/${run.run_id}`}>{formatYmd(run.batch_ymd)}</Link>
                </td>
                <td>{run.run_mode}</td>
                <td>
                  <CodeLabel value={run.run_stat_cd} />
                </td>
                <td className="num">{run.total_cnt}</td>
                <td className="num">{run.change_detected_cnt}</td>
                <td>{formatInstant(run.started_at)}</td>
                <td>{run.ended_at ? formatInstant(run.ended_at) : <span className="muted">진행 중</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
