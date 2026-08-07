/**
 * S-20 감사 로그 조회.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-20 (쓰기 **없음**, `audit:read`)
 *       DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §15 §19.1
 *
 * **읽기 전용이다.** 수정·삭제 버튼을 두지 않는다 — append-only 이며 런타임
 * 롤에 UPDATE·DELETE 가 아예 없다(§15).
 *
 * `audit:read` 는 `user:manage` 와 **분리된 권한**이다. 설계 §5 가 AUDITOR 와
 * ADMIN 을 갈라놨기 때문에, ADMIN 계정으로는 이 화면이 403 이 된다. 버그가
 * 아니라 직무 분리다 — 오해하지 않도록 403 을 그렇게 설명한다.
 *
 * 실패한 시도(`DENIED`)가 성공과 같은 표에 섞여 나온다. 거부야말로 보안
 * 신호이므로 기본 필터로 감추지 않는다.
 */

import { useCallback, useEffect, useState } from 'react'

import { ApiError, api, buildQuery } from '../api/client'
import { Empty, ErrorBanner, Loading, Pager, formatInstant } from '../components/common'

const LIMIT = 50

const RESULT_TONE: Record<string, string> = {
  SUCCESS: 'badge-ok',
  DENIED: 'badge-warn',
  FAILED: 'badge-error',
  TIMEOUT: 'badge-warn',
}

interface Entry {
  audit_id: number
  occurred_at: string
  actor: string
  actor_role_cd: string | null
  source_ip: string | null
  action: string
  target_type: string | null
  target_id: string | null
  before_value: unknown
  after_value: unknown
  reason: string | null
  result_cd: string
}

interface Page {
  items: Entry[]
  limit: number
  offset: number
  has_more: boolean
}

function Values({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null
  return (
    <div className="audit-val">
      <span className="audit-val-label">{label}</span>
      <code>{JSON.stringify(value)}</code>
    </div>
  )
}

export function AuditScreen() {
  const [page, setPage] = useState<Page | null>(null)
  const [actions, setActions] = useState<string[]>([])
  const [error, setError] = useState<unknown>(null)
  const [offset, setOffset] = useState(0)
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [resultCd, setResultCd] = useState('')
  const [openRow, setOpenRow] = useState<number | null>(null)

  const query = buildQuery({ actor, action, result_cd: resultCd, limit: LIMIT, offset })

  useEffect(() => {
    setPage(null)
    setError(null)
    void api
      .get<Page>(`/api/admin/audit${query}`)
      .then(setPage)
      .catch(setError)
  }, [query])

  useEffect(() => {
    void api
      .get<{ items: string[] }>('/api/admin/audit/actions')
      .then((r) => setActions(r.items))
      .catch(() => setActions([]))
  }, [])

  const setFilter = useCallback((apply: () => void) => {
    apply()
    setOffset(0)
  }, [])

  // 403 은 권한 부족이며 직무 분리의 결과다. 로그인 문제로 오해하지 않게 설명한다.
  if (error instanceof ApiError && error.isForbidden) {
    return (
      <div className="screen">
        <h2>감사 로그</h2>
        <div className="banner banner-error">
          이 화면에는 <code>audit:read</code> 권한이 필요합니다. 설계 §5 는 감사 열람을 관리자
          권한과 분리하므로, ADMIN 계정에는 기본적으로 이 권한이 없습니다. AUDITOR 역할을 가진
          계정으로 접속하세요.
        </div>
      </div>
    )
  }
  if (error) return <ErrorBanner error={error} />

  return (
    <div className="screen">
      <h2>감사 로그</h2>
      <p className="muted">
        읽기 전용입니다. 거부·실패한 시도도 함께 표시합니다. 비밀번호와 토큰은 기록 시점에
        마스킹됩니다.
      </p>

      <div className="filters">
        <label className="filter">
          <span>행위자</span>
          <input
            value={actor}
            placeholder="로그인 ID 일부"
            onChange={(event) => setFilter(() => setActor(event.target.value))}
          />
        </label>
        <label className="filter">
          <span>작업</span>
          <select value={action} onChange={(e) => setFilter(() => setAction(e.target.value))}>
            <option value="">전체</option>
            {actions.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span>결과</span>
          <select value={resultCd} onChange={(e) => setFilter(() => setResultCd(e.target.value))}>
            <option value="">전체</option>
            <option value="SUCCESS">성공</option>
            <option value="DENIED">거부</option>
            <option value="FAILED">실패</option>
            <option value="TIMEOUT">타임아웃</option>
          </select>
        </label>
      </div>

      {!page ? <Loading what="감사 로그를" /> : null}
      {page && page.items.length === 0 ? <Empty message="조건에 맞는 기록이 없습니다." /> : null}

      {page && page.items.length > 0 ? (
        <div className="panel">
          <table className="grid">
            <thead>
              <tr>
                <th>시각</th>
                <th>행위자</th>
                <th>작업</th>
                <th>대상</th>
                <th>결과</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((entry) => (
                <tr
                  key={entry.audit_id}
                  className="is-clickable"
                  onClick={() => setOpenRow(openRow === entry.audit_id ? null : entry.audit_id)}
                >
                  <td className="mono">{formatInstant(entry.occurred_at)}</td>
                  <td>
                    <div className="row-date">{entry.actor}</div>
                    <div className="row-sub">{entry.actor_role_cd ?? '—'}</div>
                  </td>
                  <td className="mono">{entry.action}</td>
                  <td className="mono">
                    {entry.target_type ? `${entry.target_type}/${entry.target_id ?? '-'}` : '—'}
                  </td>
                  <td>
                    <span className={`badge ${RESULT_TONE[entry.result_cd] ?? ''}`}>
                      {entry.result_cd}
                    </span>
                  </td>
                  <td>
                    <div className="audit-reason">{entry.reason ?? '—'}</div>
                    {openRow === entry.audit_id ? (
                      <div className="audit-detail">
                        <Values label="변경 전" value={entry.before_value} />
                        <Values label="변경 후" value={entry.after_value} />
                        {entry.source_ip ? (
                          <div className="audit-val">
                            <span className="audit-val-label">출처 IP</span>
                            <code>{entry.source_ip}</code>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {page ? (
        <Pager
          offset={page.offset}
          limit={page.limit}
          hasMore={page.has_more}
          onChange={setOffset}
        />
      ) : null}
    </div>
  )
}
