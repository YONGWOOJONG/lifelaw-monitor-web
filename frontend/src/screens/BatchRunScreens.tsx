/**
 * S-10 배치 실행 원장, S-11 배치 실행 상세.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-10 S-11
 *
 * 읽기 전용이다. rerun·취소 같은 실행 제어는 6단계 명령 Inbox 소관이며,
 * 이 화면에는 실행 제어 버튼을 두지 않는다.
 */

import { useEffect, useState } from 'react'

import { api, buildQuery } from '../api/client'
import type { BatchRunRow, PageEnvelope } from '../api/types'
import { Link } from '../app/router'
import {
  CodeLabel,
  Empty,
  ErrorBanner,
  Field,
  Loading,
  Pager,
  formatInstant,
  formatYmd,
} from '../components/common'

const LIMIT = 25

function RunState({ code, endedAt }: { code: string; endedAt: string | null }) {
  // 6010 대기 / 6020 실행중은 종료 시각이 없다. 진행 중임을 분명히 표시한다.
  const running = code === '6010' || code === '6020'
  return (
    <>
      <CodeLabel value={code} />
      {running && !endedAt ? <span className="badge badge-running">진행 중</span> : null}
    </>
  )
}

export function BatchRunListScreen() {
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<PageEnvelope<BatchRunRow> | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    setPage(null)
    void api
      .get<PageEnvelope<BatchRunRow>>(`/api/batch-runs${buildQuery({ limit: LIMIT, offset })}`)
      .then(setPage)
      .catch(setError)
  }, [offset])

  if (error) return <ErrorBanner error={error} />
  if (!page) return <Loading what="배치 실행 원장을" />
  if (page.items.length === 0) return <Empty message="배치 실행 기록이 없습니다." />

  return (
    <div className="screen">
      <h2>배치 실행 원장</h2>
      <table className="grid">
        <thead>
          <tr>
            <th>업무일자</th>
            <th>모드</th>
            <th>상태</th>
            <th className="num">전체</th>
            <th className="num">성공</th>
            <th className="num">실패</th>
            <th className="num">변경</th>
            <th className="num">제외</th>
            <th>시작</th>
          </tr>
        </thead>
        <tbody>
          {page.items.map((run) => (
            <tr key={run.run_id}>
              <td>
                <Link to={`/batch-runs/${run.run_id}`}>{formatYmd(run.batch_ymd)}</Link>
              </td>
              <td>{run.run_mode}</td>
              <td>
                <RunState code={run.run_stat_cd} endedAt={run.ended_at} />
              </td>
              <td className="num">{run.total_cnt}</td>
              <td className="num">{run.success_cnt}</td>
              <td className="num">{run.fail_cnt}</td>
              <td className="num">{run.change_detected_cnt}</td>
              <td className="num">{run.excluded_cnt}</td>
              <td>{formatInstant(run.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pager offset={page.offset} limit={page.limit} hasMore={page.has_more} onChange={setOffset} />
    </div>
  )
}

export function BatchRunDetailScreen({ runId }: { runId: number }) {
  const [run, setRun] = useState<BatchRunRow | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    setRun(null)
    void api
      .get<BatchRunRow>(`/api/batch-runs/${runId}`)
      .then(setRun)
      .catch(setError)
  }, [runId])

  if (error) return <ErrorBanner error={error} />
  if (!run) return <Loading what="배치 실행 상세를" />

  return (
    <div className="screen">
      <div className="crumbs">
        <Link to="/batch-runs">← 배치 실행 원장</Link>
      </div>
      <h2>
        {formatYmd(run.batch_ymd)} · {run.run_mode}
      </h2>
      <div className="panel">
        <div className="fields">
          <Field label="실행 번호">{run.run_id}</Field>
          <Field label="실행 모드">{run.run_mode}</Field>
          <Field label="상태">
            <RunState code={run.run_stat_cd} endedAt={run.ended_at} />
          </Field>
          <Field label="시작">{formatInstant(run.started_at)}</Field>
          <Field label="종료">
            {run.ended_at ? formatInstant(run.ended_at) : <span className="muted">진행 중</span>}
          </Field>
        </div>
      </div>
      <div className="panel">
        <h3>집계</h3>
        <div className="fields">
          <Field label="전체">{run.total_cnt}</Field>
          <Field label="성공">{run.success_cnt}</Field>
          <Field label="실패">{run.fail_cnt}</Field>
          <Field label="변경 감지">{run.change_detected_cnt}</Field>
          <Field label="오류">{run.err_cnt}</Field>
          <Field label="수집 제외">{run.excluded_cnt}</Field>
        </div>
        <p className="muted">
          집계는 수집기가 기록한 값입니다. 이 화면은 조회 전용이며 실행 제어
          기능을 제공하지 않습니다.
        </p>
      </div>
    </div>
  )
}
