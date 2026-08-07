/**
 * S-16 R 마스터 조회, S-17 공통 코드 조회, S-21 계약·스키마 상태.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-16 S-17 S-21
 *
 * 셋 다 읽기 전용이다. 특히 공통 코드는 추가·수정·삭제·`use_yn` 토글 UI 를
 * 제공하지 않는다(설계 §14). 코드값의 단일 출처는 G1 이고 DB 는 사본이다.
 */

import { useEffect, useState } from 'react'

import { api, buildQuery } from '../api/client'
import type { CommonCode, ContractStatus, PageEnvelope, Row, SitePolicy } from '../api/types'
import { useCodes } from '../app/CodeContext'
import {
  CodeLabel,
  Empty,
  ErrorBanner,
  Loading,
  Pager,
  PolicyBadge,
  formatInstant,
} from '../components/common'

const LIMIT = 50

export function LinkScreen() {
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<PageEnvelope<Row> | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    setPage(null)
    void api
      .get<PageEnvelope<Row>>(`/api/links${buildQuery({ limit: LIMIT, offset })}`)
      .then(setPage)
      .catch(setError)
  }, [offset])

  if (error) return <ErrorBanner error={error} />
  if (!page) return <Loading what="R 마스터를" />
  if (page.items.length === 0) return <Empty message="링크 마스터가 비어 있습니다." />

  return (
    <div className="screen">
      <h2>R 마스터 (관심규정 관련링크)</h2>
      <p className="muted">
        R 시스템 원본의 사본입니다. R1 동기화가 유일한 작성자이며 이 화면은 조회 전용입니다.
      </p>
      <table className="grid">
        <thead>
          <tr>
            <th className="num">링크 번호</th>
            <th>이름</th>
            <th>분류</th>
            <th>URL</th>
            <th className="num">대상 번호</th>
            <th>수정</th>
          </tr>
        </thead>
        <tbody>
          {page.items.map((row) => (
            <tr key={String(row.con_link_seq)}>
              <td className="num">{String(row.con_link_seq)}</td>
              <td>{String(row.con_link_nm)}</td>
              <td>
                <CodeLabel value={row.con_link_class_cd as string} />
              </td>
              <td className="sub">{String(row.con_link_url)}</td>
              <td className="num">{row.url_id ? String(row.url_id) : <span className="muted">—</span>}</td>
              <td>{formatInstant(row.mod_dt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pager offset={page.offset} limit={page.limit} hasMore={page.has_more} onChange={setOffset} />
    </div>
  )
}

export function CodeScreen() {
  const { codes, loaded } = useCodes()
  if (!loaded) return <Loading what="공통 코드를" />

  const groups = [...new Set(codes.map((code) => code.code_grp_cd))]
  return (
    <div className="screen">
      <h2>공통 코드</h2>
      <p className="muted">
        읽기 전용입니다. 코드값의 단일 출처는 승인된 용어·코드 정의이며 이 화면에서
        추가·수정·삭제하지 않습니다.
      </p>
      {groups.map((group) => (
        <div className="panel" key={group}>
          <h3>{group}</h3>
          <table className="grid">
            <thead>
              <tr>
                <th>코드값</th>
                <th>명칭</th>
                <th>상수명</th>
              </tr>
            </thead>
            <tbody>
              {codes
                .filter((code: CommonCode) => code.code_grp_cd === group)
                .map((code) => (
                  <tr key={`${code.code_grp_cd}-${code.code_val}`}>
                    <td>
                      <code>{code.code_val}</code>
                    </td>
                    <td>{code.code_nm}</td>
                    <td className="sub">{code.code_const ?? '—'}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

export function SitePolicyScreen() {
  const [items, setItems] = useState<SitePolicy[] | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    void api
      .get<{ items: SitePolicy[] }>('/api/site-policies')
      .then((result) => setItems(result.items))
      .catch(setError)
  }, [])

  if (error) return <ErrorBanner error={error} />
  if (!items) return <Loading what="사이트 정책을" />

  return (
    <div className="screen">
      <h2>사이트 수집 정책</h2>
      <p className="muted">
        조회 전용입니다. 정책 변경은 배리어·승인 절차를 갖춘 별도 화면에서 수행합니다.
      </p>
      <table className="grid">
        <thead>
          <tr>
            <th>사이트</th>
            <th>정책</th>
            <th className="num">버전</th>
            <th className="num">대상 수</th>
            <th>사유</th>
            <th>수정</th>
          </tr>
        </thead>
        <tbody>
          {items.map((policy) => (
            <tr key={policy.site_policy_id}>
              <td>{policy.site_host}</td>
              <td>
                <PolicyBadge kind="effective" value={policy.collect_policy_cd} />
              </td>
              <td className="num">{policy.policy_version}</td>
              <td className="num">{policy.target_cnt}</td>
              <td className="sub">{policy.policy_reason ?? '—'}</td>
              <td>{formatInstant(policy.mod_dt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ContractStatusScreen() {
  const [status, setStatus] = useState<ContractStatus | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    void api
      .get<ContractStatus>('/api/status/contract')
      .then(setStatus)
      .catch(setError)
  }, [])

  if (error) return <ErrorBanner error={error} />
  if (!status) return <Loading what="계약 상태를" />

  return (
    <div className="screen">
      <h2>계약·스키마 상태</h2>
      <div className="panel">
        <h3>고정된 계약 버전</h3>
        <div className="fields">
          <div className="field">
            <div className="field-label">C1</div>
            <div className="field-value">{status.pin.c1_version}</div>
          </div>
          <div className="field">
            <div className="field-label">G1</div>
            <div className="field-value">{status.pin.g1_version}</div>
          </div>
          <div className="field">
            <div className="field-label">DDL</div>
            <div className="field-value sub">{status.pin.ddl_filename}</div>
          </div>
          <div className="field">
            <div className="field-label">마이그레이션</div>
            <div className="field-value">{status.pin.expected_migration}</div>
          </div>
        </div>
      </div>

      <div className={`banner ${status.all_passed ? 'banner-ok' : 'banner-error'}`}>
        {status.all_passed
          ? '모든 계약 검증을 통과했습니다.'
          : `계약 불일치 ${status.failed_count}건 — 이 상태에서는 기능을 열지 않습니다.`}
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th>검사</th>
            <th>항목</th>
            <th>결과</th>
            <th>상세</th>
          </tr>
        </thead>
        <tbody>
          {status.checks.map((check) => (
            <tr key={`${check.check_id}-${check.title}`}>
              <td>
                <code>{check.check_id}</code>
              </td>
              <td>{check.title}</td>
              <td>
                {check.informational ? (
                  <span className="badge">참고</span>
                ) : check.ok ? (
                  <span className="badge badge-collect">통과</span>
                ) : (
                  <span className="badge badge-excluded">실패</span>
                )}
              </td>
              <td className="sub">{check.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
