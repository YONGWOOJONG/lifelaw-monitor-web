/**
 * S-04 수집 대상 목록.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-04
 *
 * 규칙:
 *  - **인라인 편집 없음.** 쓰기는 전용 화면(5단계)에서만 한다.
 *  - 계산 컬럼은 표시만 한다. OR 규칙을 여기서 재구현하지 않는다.
 *  - 전체 건수는 목록과 **별도 요청**이다. 필요할 때만 부른다.
 *  - 각 행의 `target_policy_version` 은 S-09 일괄 변경의 입력이므로 항상 받는다.
 */

import { useCallback, useEffect, useState } from 'react'

import { api, buildQuery } from '../api/client'
import type { CountResponse, PageEnvelope, SitePolicy, TargetRow } from '../api/types'
import { useCodes } from '../app/CodeContext'
import { Link } from '../app/router'
import {
  CodeLabel,
  Empty,
  ErrorBanner,
  Loading,
  Pager,
  PolicyBadge,
  formatYmd,
} from '../components/common'

const LIMIT = 50

interface Filters {
  site_host: string
  link_class_cd: string
  crawl_stat_cd: string
  change_yn_cd: string
  execution_collect_policy_cd: string
  has_diagnostic: string
}

const EMPTY_FILTERS: Filters = {
  site_host: '',
  link_class_cd: '',
  crawl_stat_cd: '',
  change_yn_cd: '',
  execution_collect_policy_cd: '',
  has_diagnostic: '',
}

function CodeSelect({
  label,
  group,
  value,
  onChange,
}: {
  label: string
  group: string
  value: string
  onChange: (value: string) => void
}) {
  const { group: byGroup } = useCodes()
  return (
    <label className="filter">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">전체</option>
        {byGroup(group).map((code) => (
          <option key={code.code_val} value={code.code_val}>
            {code.code_nm}
          </option>
        ))}
      </select>
    </label>
  )
}

export function TargetListScreen() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('url_id')
  const [page, setPage] = useState<PageEnvelope<TargetRow> | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [hosts, setHosts] = useState<SitePolicy[]>([])
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    void api
      .get<{ items: SitePolicy[] }>('/api/site-policies')
      .then((result) => setHosts(result.items))
      .catch(() => setHosts([]))
  }, [])

  const query = buildQuery({ ...filters, limit: LIMIT, offset, sort })

  useEffect(() => {
    setPage(null)
    setError(null)
    void api
      .get<PageEnvelope<TargetRow>>(`/api/targets${query}`)
      .then(setPage)
      .catch(setError)
  }, [query])

  const setFilter = useCallback((key: keyof Filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }))
    setOffset(0)
    setTotal(null)
  }, [])

  const loadTotal = useCallback(() => {
    const countQuery = buildQuery({ ...filters })
    void api
      .get<CountResponse>(`/api/targets/count${countQuery}`)
      .then((result) => setTotal(result.count))
      .catch(() => setTotal(null))
  }, [filters])

  return (
    <div className="screen">
      <h2>수집 대상</h2>

      <div className="filters">
        <label className="filter">
          <span>사이트</span>
          <select
            value={filters.site_host}
            onChange={(event) => setFilter('site_host', event.target.value)}
          >
            <option value="">전체</option>
            {hosts.map((host) => (
              <option key={host.site_policy_id} value={host.site_host}>
                {host.site_host}
              </option>
            ))}
          </select>
        </label>
        <CodeSelect
          label="링크 분류"
          group="LINK_CLASS"
          value={filters.link_class_cd}
          onChange={(value) => setFilter('link_class_cd', value)}
        />
        <CodeSelect
          label="수집 상태"
          group="CRAWL_STAT"
          value={filters.crawl_stat_cd}
          onChange={(value) => setFilter('crawl_stat_cd', value)}
        />
        <CodeSelect
          label="변경 판정"
          group="CHANGE_YN"
          value={filters.change_yn_cd}
          onChange={(value) => setFilter('change_yn_cd', value)}
        />
        <CodeSelect
          label="실행 정책"
          group="COLLECT_POLICY"
          value={filters.execution_collect_policy_cd}
          onChange={(value) => setFilter('execution_collect_policy_cd', value)}
        />
        <label className="filter">
          <span>진단</span>
          <select
            value={filters.has_diagnostic}
            onChange={(event) => setFilter('has_diagnostic', event.target.value)}
          >
            <option value="">전체</option>
            <option value="true">진단 있음</option>
            <option value="false">진단 없음</option>
          </select>
        </label>
        <label className="filter">
          <span>정렬</span>
          <select value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="url_id">대상 번호</option>
            <option value="-mod_dt">최근 수정순</option>
            <option value="crawl_stat">수집 상태</option>
            <option value="change_yn">변경 판정</option>
            <option value="policy">실행 정책</option>
          </select>
        </label>
        <button type="button" onClick={() => setFilters(EMPTY_FILTERS)}>
          필터 초기화
        </button>
      </div>

      <div className="toolbar">
        {total === null ? (
          <button type="button" onClick={loadTotal}>
            전체 건수 조회
          </button>
        ) : (
          <span className="muted">전체 {total.toLocaleString('ko-KR')}건</span>
        )}
      </div>

      <ErrorBanner error={error} />
      {!page && !error ? <Loading what="대상 목록을" /> : null}
      {page && page.items.length === 0 ? <Empty message="조건에 맞는 대상이 없습니다." /> : null}

      {page && page.items.length > 0 ? (
        <>
          <table className="grid">
            <thead>
              <tr>
                <th>대상</th>
                <th>사이트</th>
                <th>분류</th>
                <th>업무일자</th>
                <th>수집</th>
                <th>변경 판정</th>
                <th>정책</th>
                <th>진단</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((row) => (
                <tr key={row.url_id}>
                  <td>
                    <Link to={`/targets/${row.url_id}`}>#{row.url_id}</Link>
                    <div className="sub">{row.con_link_url}</div>
                  </td>
                  <td>{row.site_host ?? <span className="muted">—</span>}</td>
                  <td>
                    <CodeLabel value={row.link_class_cd} />
                  </td>
                  <td>{formatYmd(row.batch_ymd)}</td>
                  <td>
                    <CodeLabel value={row.crawl_stat_cd} />
                  </td>
                  <td>
                    <CodeLabel value={row.change_yn_cd} />
                  </td>
                  <td>
                    {/* 구성 정책과 실행 정책은 다른 값이다. 둘 다 보여준다. */}
                    <PolicyBadge kind="effective" value={row.effective_collect_policy_cd} />{' '}
                    <PolicyBadge kind="execution" value={row.execution_collect_policy_cd} />
                  </td>
                  <td>
                    {row.crawl_diag_cd ? <CodeLabel value={row.crawl_diag_cd} /> : <span className="muted">—</span>}
                  </td>
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
      ) : null}
    </div>
  )
}
