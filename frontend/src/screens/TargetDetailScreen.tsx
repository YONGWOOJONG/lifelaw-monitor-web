/**
 * S-05 수집 대상 상세 + S-06 변경 이력.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-05 S-06
 *
 * 규칙:
 *  - `crawl_candidate_url` 은 **표시만** 한다. "이 URL 로 교체" 버튼을 제공하지
 *    않는다(설계 §16, 참조 저장소 D-32).
 *  - 해시는 표시 전용이다.
 *  - 이력 조회 가능 범위를 명시하고, 범위 밖의 0건을 "데이터 없음"과 구분한다.
 */

import { useEffect, useState } from 'react'

import { api, buildQuery } from '../api/client'
import type { HistoryPage, Row } from '../api/types'
import { useAuth } from '../app/AuthContext'
import { Link } from '../app/router'
import {
  CodeLabel,
  Empty,
  ErrorBanner,
  Field,
  Loading,
  Pager,
  PolicyBadge,
  formatInstant,
  formatYmd,
} from '../components/common'

const HISTORY_LIMIT = 20

function Hash({ value }: { value: unknown }) {
  if (typeof value !== 'string' || !value) return <span className="muted">—</span>
  return (
    <code className="hash" title={value}>
      {value.slice(0, 16)}…
    </code>
  )
}

function HistorySection({ urlId }: { urlId: number }) {
  const { can } = useAuth()
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<HistoryPage | null>(null)
  const [error, setError] = useState<unknown>(null)

  const allowed = can('target:history:read')

  useEffect(() => {
    if (!allowed) return
    setPage(null)
    void api
      .get<HistoryPage>(`/api/targets/${urlId}/history${buildQuery({ limit: HISTORY_LIMIT, offset })}`)
      .then(setPage)
      .catch(setError)
  }, [urlId, offset, allowed])

  if (!allowed) {
    return (
      <div className="panel">
        <h3>변경 이력</h3>
        <div className="muted pad">
          이력을 볼 권한이 없습니다. 필요한 권한: <code>target:history:read</code>
        </div>
      </div>
    )
  }

  return (
    <div className="panel">
      <h3>변경 이력</h3>
      <ErrorBanner error={error} />
      {!page && !error ? <Loading what="이력을" /> : null}
      {page ? (
        <>
          <p className="muted">
            조회 가능 범위: {page.available_months.map((m) => `${m.slice(0, 4)}-${m.slice(4)}`).join(', ') || '없음'}
            {' · '}보존 정책상 이 범위 밖은 조회할 수 없습니다(현재 업무월 + 직전 2개월).
          </p>
          {page.items.length === 0 ? (
            <Empty message="이 범위에 남은 이력이 없습니다. 범위 밖 기간은 보존 정책에 따라 조회 대상이 아닙니다." />
          ) : (
            <>
              <table className="grid">
                <thead>
                  <tr>
                    <th>업무일자</th>
                    <th>수집</th>
                    <th>변경 판정</th>
                    <th>실행 정책</th>
                    <th>원본 해시</th>
                    <th>스냅샷</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((row) => (
                    <tr key={String(row.batch_ymd)}>
                      <td>{formatYmd(row.batch_ymd)}</td>
                      <td>
                        <CodeLabel value={row.crawl_stat_cd as string | null} />
                      </td>
                      <td>
                        <CodeLabel value={row.change_yn_cd as string | null} />
                      </td>
                      <td>
                        <PolicyBadge
                          kind="execution"
                          value={String(row.execution_collect_policy_cd)}
                        />
                      </td>
                      <td>
                        <Hash value={row.raw_html_hash} />
                      </td>
                      <td>{formatInstant(row.snap_dt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pager
                offset={page.offset}
                limit={page.limit}
                hasMore={page.has_more}
                onChange={setOffset}
              />
            </>
          )}
        </>
      ) : null}
    </div>
  )
}

export function TargetDetailScreen({ urlId }: { urlId: number }) {
  const [target, setTarget] = useState<Row | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    setTarget(null)
    setError(null)
    void api
      .get<Row>(`/api/targets/${urlId}`)
      .then(setTarget)
      .catch(setError)
  }, [urlId])

  if (error) return <ErrorBanner error={error} />
  if (!target) return <Loading what="대상 상세를" />

  const candidateUrl = target.crawl_candidate_url as string | null

  return (
    <div className="screen">
      <div className="crumbs">
        <Link to="/targets">← 대상 목록</Link>
      </div>
      <h2>대상 #{String(target.url_id)}</h2>
      <p className="url">{String(target.con_link_url)}</p>

      <div className="panel">
        <h3>기본</h3>
        <div className="fields">
          <Field label="링크 이름">{String(target.con_link_nm ?? '—')}</Field>
          <Field label="R 링크 번호">{String(target.con_link_seq)}</Field>
          <Field label="사이트">{String(target.site_host ?? '—')}</Field>
          <Field label="링크 분류">
            <CodeLabel value={target.link_class_cd as string} />
          </Field>
          <Field label="대상 종류">
            <CodeLabel value={target.collect_target_kind_cd as string | null} />
          </Field>
          <Field label="업무일자">{formatYmd(target.batch_ymd)}</Field>
        </div>
      </div>

      <div className="panel">
        <h3>수집 정책</h3>
        <div className="fields">
          <Field label="사이트 상속">
            <CodeLabel value={target.site_collect_policy_cd as string} />
          </Field>
          <Field label="대상 직접">
            <CodeLabel value={target.target_collect_policy_cd as string} />
          </Field>
          <Field label="실행 중 제외">
            <CodeLabel value={target.run_collect_policy_cd as string} />
          </Field>
          <Field label="구성 정책 (계산)">
            <PolicyBadge kind="effective" value={String(target.effective_collect_policy_cd)} />
          </Field>
          <Field label="실행 정책 (계산)">
            <PolicyBadge kind="execution" value={String(target.execution_collect_policy_cd)} />
          </Field>
          <Field label="대상 정책 버전">{String(target.target_policy_version)}</Field>
        </div>
        <p className="muted">
          구성 정책은 사이트·대상 설정의 합성이고, 실행 정책은 여기에 실행 중 redirect
          제외까지 반영한 값입니다. 두 값은 서버가 계산해 저장하며 화면은 표시만 합니다.
        </p>
      </div>

      <div className="panel">
        <h3>처리 상태</h3>
        <div className="fields">
          <Field label="수집">
            <CodeLabel value={target.crawl_stat_cd as string} />
          </Field>
          <Field label="추출">
            <CodeLabel value={target.extract_stat_cd as string} />
          </Field>
          <Field label="정규화">
            <CodeLabel value={target.norm_stat_cd as string} />
          </Field>
          <Field label="비교">
            <CodeLabel value={target.cmpr_stat_cd as string} />
          </Field>
          <Field label="변경 판정">
            <CodeLabel value={target.change_yn_cd as string} />
          </Field>
        </div>
        {target.crawl_err_msg ? (
          <div className="banner banner-warn">수집 오류: {String(target.crawl_err_msg)}</div>
        ) : null}
      </div>

      {target.crawl_diag_cd ? (
        <div className="panel">
          <h3>진단</h3>
          <div className="fields">
            <Field label="진단 코드">
              <CodeLabel value={target.crawl_diag_cd as string} />
            </Field>
            <Field label="메시지">{String(target.crawl_diag_msg ?? '—')}</Field>
            <Field label="후보 URL">{candidateUrl ?? '—'}</Field>
          </div>
          <p className="muted">
            후보 URL 은 진단 정보입니다. 이 화면에서 등록 URL 을 바꾸지 않습니다 —
            자동 URL 교체는 R 계약상 금지되어 있습니다.
          </p>
        </div>
      ) : null}

      <div className="panel">
        <h3>해시</h3>
        <div className="fields">
          <Field label="원본">
            <Hash value={target.raw_html_hash} />
          </Field>
          <Field label="정규화">
            <Hash value={target.norm_html_hash} />
          </Field>
          <Field label="기준선 원본">
            <Hash value={target.prev_raw_hash} />
          </Field>
          <Field label="기준선 정규화">
            <Hash value={target.prev_norm_hash} />
          </Field>
        </div>
      </div>

      <HistorySection urlId={urlId} />
    </div>
  )
}
