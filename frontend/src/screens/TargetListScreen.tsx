/**
 * S-04 수집 대상 목록.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-04
 *
 * 규칙(원본에서 그대로 유지):
 *  - **인라인 편집 없음.** 쓰기는 전용 화면(5단계)에서만 한다.
 *  - 계산 컬럼은 표시만 한다. OR 규칙을 여기서 재구현하지 않는다.
 *  - 전체 건수는 목록과 **별도 요청**이다. 필요할 때만 부른다.
 *  - 각 행의 `target_policy_version` 은 S-09 일괄 변경의 입력이므로 항상 받는다.
 *
 * 3a 시안:
 *  - **단계마다 컬럼 하나.** 수집·추출·정규화·비교를 나란히 세워 "어디서
 *    떨어졌나"를 세로로 훑게 한다. 원래는 수집 상태 하나만 보였고, 추출·정규화·
 *    비교는 상세 화면에 들어가야만 알 수 있었다.
 *  - 색조는 `app/tones.ts` 한 곳에서 온다. 운영 현황과 같은 표를 쓴다 —
 *    두 화면이 같은 코드를 다른 색으로 그리면 색을 신뢰할 수 없다.
 *  - 필터를 흰 패널로 묶고, 정렬·초기화는 구분선 오른쪽에 뒀다. 정렬은
 *    필터가 아니라 표시 옵션이다.
 *  - 한 쪽 10건. 50건은 스크롤 없이 훑을 수 없고, 이 화면은 훑는 화면이다.
 *
 * 여전히 하드코딩하지 않는 것: 코드 라벨. 전부 `label()`(=`TC_COMMON_CODE`)에서
 * 온다. 단계 셀에는 명칭만 쓰고 코드값은 툴팁에 남긴다 — 컬럼이 좁아서 둘 다는
 * 안 들어가지만, 계약 코드를 확인해야 하는 순간은 있다.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { api, buildQuery } from '../api/client'
import type { CountResponse, PageEnvelope, SitePolicy, TargetRow } from '../api/types'
import { useCodes } from '../app/CodeContext'
import { Link, useRouter, useSearchParams } from '../app/router'
import { changeTone, stageTone } from '../app/tones'
import type { SegTone } from '../app/tones'
import { CodeLabel, Empty, ErrorBanner, Loading, Pager, PolicyBadge } from '../components/common'

/** 한 쪽 10건. 훑는 화면이므로 스크롤 없이 끝까지 보이는 쪽을 택했다. */
const LIMIT = 10

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

/**
 * 쿼리스트링에서 진입 필터를 읽는다. 대시보드 알림 카드가 이 경로로 들어온다.
 *
 * 키 이름은 **API 파라미터와 같다.** 별칭(`diagnostic`, `excluded` 같은)을 두면
 * 변환표가 하나 더 생기고, 그 표가 API 와 어긋나도 아무도 모른다.
 */
function filtersFrom(params: URLSearchParams): Filters {
  const pick = (key: keyof Filters): string => params.get(key) ?? ''
  return {
    site_host: pick('site_host'),
    link_class_cd: pick('link_class_cd'),
    crawl_stat_cd: pick('crawl_stat_cd'),
    change_yn_cd: pick('change_yn_cd'),
    execution_collect_policy_cd: pick('execution_collect_policy_cd'),
    has_diagnostic: pick('has_diagnostic'),
  }
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

/**
 * 단계 셀에 쓸 짧은 표기 — 명칭의 **마지막 낱말**만 남긴다.
 *
 * 코드 명칭은 `단계 + 결과` 구조다("크롤링 성공", "본문 컨텐츠 추출 성공").
 * 단계는 이미 컬럼 머리글에 있으니 매 칸에 되풀이할 이유가 없다. 되풀이하면
 * 62px 컬럼에서 두세 줄로 접혀 네 칸이 글자로 꽉 찬다(실측 40칸 중 34칸).
 *
 * 행 높이를 줄이려는 것이 아니다 — 행은 `대상`(번호 + 경로)과 `정책`(배지 둘)이
 * 원래 두 줄이라 61px 이고, 단계 칸이 접히든 안 접히든 그대로다. 노리는 것은
 * 세로로 훑을 때 눈에 걸리는 것을 줄이는 쪽이다.
 *
 * **색을 정하는 규칙과 성격이 다르다.** 이건 표시만 줄이고 뜻은 건드리지 않는다.
 * 규칙이 어긋나도 최악이 전체 명칭이 나오는 것이며, 전체 명칭은 툴팁에 늘 있다.
 * 색조 규칙이 틀리면 조용히 틀린 색이 나오지만, 이건 틀려도 눈에 보인다.
 */
function shortLabel(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts[parts.length - 1] || name
}

/**
 * 단계 상태 한 칸.
 *
 * 비대상(`x000`)은 명칭 대신 `—` 를 쓴다. "비대상"이라고 적으면 네 컬럼이
 * 글자로 가득 차서, 정작 봐야 할 실패·대기가 묻힌다. 무슨 뜻인지는 표 위에
 * 한 줄로 적어두고, 툴팁에 코드와 명칭을 남긴다.
 */
function StageCell({ code }: { code: string }) {
  const { label } = useCodes()
  const tone: SegTone = stageTone(code)
  const title = `${code} ${label(code)}`
  if (tone === 'none') {
    return (
      <span className="stage stage-none" title={title}>
        —
      </span>
    )
  }
  return (
    <span className={`stage stage-${tone}`} title={title}>
      {shortLabel(label(code))}
    </span>
  )
}

/** 변경 판정 한 칸. 단계와 다른 색조 표를 쓴다(접미 규칙이 이 그룹에서 뒤집힌다). */
function ChangeCell({ code }: { code: string }) {
  const { label } = useCodes()
  return (
    <span className={`stage stage-${changeTone(code)}`} title={`${code} ${label(code)}`}>
      {label(code)}
    </span>
  )
}

/**
 * 목록에서는 경로만 보여준다. 사이트는 옆 컬럼에 이미 있고, `https://` 와
 * 호스트가 매 행 반복되면 정작 다른 부분인 경로가 잘려 나간다. 전체 URL 은
 * 툴팁과 상세 화면에 있다.
 */
function pathOf(url: string): string {
  try {
    const parsed = new URL(url)
    return `${parsed.pathname}${parsed.search}` || '/'
  } catch {
    return url
  }
}

export function TargetListScreen() {
  const params = useSearchParams()
  const { navigate } = useRouter()
  // 분류 셀에서 명칭을 직접 쓴다. 라벨 출처는 여전히 `TC_COMMON_CODE` 하나다.
  const { label: classLabel } = useCodes()
  const [filters, setFilters] = useState<Filters>(() => filtersFrom(params))
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

  // 주소의 질의가 바뀔 때만 필터를 다시 읽는다. 화면 안에서 셀렉트를 만져도
  // 주소는 그대로이므로, 사용자가 고른 값을 이 effect 가 덮어쓰지 않는다.
  useEffect(() => {
    setFilters(filtersFrom(params))
    setOffset(0)
    setTotal(null)
  }, [params])

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

  // 적용 중인 필터 개수. 셀렉트가 일곱 개라 무엇이 걸려 있는지 한눈에 안 보인다.
  const activeCount = useMemo(
    () => Object.values(filters).filter((value) => value !== '').length,
    [filters],
  )

  const reset = useCallback(() => {
    setFilters(EMPTY_FILTERS)
    setOffset(0)
    setTotal(null)
    // 질의를 달고 들어왔다면 주소도 같이 비운다. 남겨두면 새로고침했을 때
    // 방금 지운 필터가 되살아난다.
    if (params.toString()) navigate('/targets', { replace: true })
  }, [navigate, params])

  return (
    <div className="screen screen-list">
      <div className="filterbar">
        <div className="filterbar-row">
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

          <div className="filterbar-gap" />

          {/* 정렬은 필터가 아니라 표시 옵션이다. 구분선 오른쪽에 따로 둔다. */}
          <div className="filterbar-sort">
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
            <button type="button" onClick={reset} disabled={activeCount === 0}>
              초기화
            </button>
          </div>
        </div>

        <div className="filterbar-foot">
          <div className="filterbar-foot-left">
            {total === null ? (
              <button type="button" onClick={loadTotal}>
                전체 건수 조회
              </button>
            ) : (
              <span className="muted">전체 {total.toLocaleString('ko-KR')}건</span>
            )}
            <span className="muted">
              {activeCount === 0 ? '필터 없음' : `필터 ${activeCount}개 적용 중`} · 대용량{' '}
              <code>COUNT</code> 를 피하려 건수는 눌러야 셉니다
            </span>
          </div>
          <span className="muted filterbar-legend">
            단계 컬럼의 <span className="stage stage-none">—</span> 는 비대상입니다. 값 없음이
            아닙니다.
          </span>
        </div>
      </div>

      <ErrorBanner error={error} />
      {!page && !error ? <Loading what="대상 목록을" /> : null}
      {page && page.items.length === 0 ? <Empty message="조건에 맞는 대상이 없습니다." /> : null}

      {page && page.items.length > 0 ? (
        <>
          <table className="grid grid-targets">
            <thead>
              <tr>
                <th className="col-target">대상</th>
                <th className="col-site">사이트</th>
                <th className="col-class">분류</th>
                {/* 네 단계를 한 묶음으로 본다. 양 끝에만 세로선을 둬서 묶음임을 보인다. */}
                <th className="col-stage is-group-start">수집</th>
                <th className="col-stage">추출</th>
                <th className="col-stage">정규화</th>
                <th className="col-stage is-group-end">비교</th>
                <th className="col-change">변경 판정</th>
                <th className="col-policy">정책</th>
                <th className="col-diag">진단</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((row) => (
                <tr key={row.url_id}>
                  <td className="col-target">
                    <Link to={`/targets/${row.url_id}`} className="cell-id">
                      #{row.url_id}
                    </Link>
                    <div className="cell-url" title={row.con_link_url}>
                      {pathOf(row.con_link_url)}
                    </div>
                  </td>
                  <td className="col-site" title={row.site_host ?? undefined}>
                    {row.site_host ?? <span className="muted">—</span>}
                  </td>
                  {/* CodeLabel 은 명칭 뒤에 코드값을 붙여 72px 에서 매 행 잘렸고,
                      툴팁에는 코드값만 있어 잘린 이름을 볼 수도 없었다. 단계 셀과
                      같은 방식으로 명칭만 쓰고 코드는 툴팁에 둔다. */}
                  <td className="col-class" title={`${row.link_class_cd} ${classLabel(row.link_class_cd)}`}>
                    {classLabel(row.link_class_cd)}
                  </td>
                  <td className="col-stage is-group-start">
                    <StageCell code={row.crawl_stat_cd} />
                  </td>
                  <td className="col-stage">
                    <StageCell code={row.extract_stat_cd} />
                  </td>
                  <td className="col-stage">
                    <StageCell code={row.norm_stat_cd} />
                  </td>
                  <td className="col-stage is-group-end">
                    <StageCell code={row.cmpr_stat_cd} />
                  </td>
                  <td className="col-change">
                    <ChangeCell code={row.change_yn_cd} />
                  </td>
                  <td className="col-policy">
                    {/* 구성 정책과 실행 정책은 다른 값이다. 둘 다 보여준다. */}
                    <PolicyBadge kind="effective" value={row.effective_collect_policy_cd} />{' '}
                    <PolicyBadge kind="execution" value={row.execution_collect_policy_cd} />
                  </td>
                  <td className="col-diag">
                    {row.crawl_diag_cd ? (
                      <span className="stage stage-warn" title={row.crawl_diag_cd}>
                        <CodeLabel value={row.crawl_diag_cd} />
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
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
