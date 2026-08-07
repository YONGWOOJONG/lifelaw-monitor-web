/**
 * 공용 표시 컴포넌트.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md
 */

import type { ReactNode } from 'react'

import { ApiError } from '../api/client'
import { useCodes } from '../app/CodeContext'

export function CodeLabel({ value }: { value: string | null | undefined }) {
  const { label } = useCodes()
  if (!value) return <span className="muted">—</span>
  return (
    <span title={value}>
      {label(value)} <span className="code">{value}</span>
    </span>
  )
}

/**
 * 수집 정책 배지.
 *
 * `effective`(구성)와 `execution`(실행)은 다른 값이다. 차이는
 * `run_collect_policy_cd` 항 하나뿐이며, 혼용하면 "제외인데 제외가 아닌"
 * 표시가 나온다(계약 §2.2). 그래서 어느 쪽인지 라벨에 항상 드러낸다.
 */
export function PolicyBadge({ kind, value }: { kind: 'effective' | 'execution'; value: string }) {
  const excluded = value === '7020'
  const scope = kind === 'effective' ? '구성' : '실행'
  return (
    <span className={`badge ${excluded ? 'badge-excluded' : 'badge-collect'}`}>
      {scope} {excluded ? '제외' : '수집'}
    </span>
  )
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null
  if (error instanceof ApiError) {
    if (error.isForbidden && error.code === 'PERMISSION_DENIED') {
      return (
        <div className="banner banner-warn">
          이 화면을 볼 권한이 없습니다.
          {error.requiredPermission ? (
            <> 필요한 권한: <code>{error.requiredPermission}</code></>
          ) : null}
        </div>
      )
    }
    return <div className="banner banner-error">{error.message}</div>
  }
  return <div className="banner banner-error">알 수 없는 오류가 발생했습니다.</div>
}

export function Loading({ what }: { what: string }) {
  return <div className="muted pad">{what} 불러오는 중…</div>
}

export function Empty({ message }: { message: string }) {
  return <div className="muted pad">{message}</div>
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <div className="field-label">{label}</div>
      <div className="field-value">{children}</div>
    </div>
  )
}

export function Pager({
  offset,
  limit,
  hasMore,
  onChange,
}: {
  offset: number
  limit: number
  hasMore: boolean
  onChange: (offset: number) => void
}) {
  const page = Math.floor(offset / limit) + 1
  return (
    <div className="pager">
      <button type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        이전
      </button>
      <span className="muted">{page} 쪽</span>
      <button type="button" disabled={!hasMore} onClick={() => onChange(offset + limit)}>
        다음
      </button>
    </div>
  )
}

export function formatInstant(value: unknown): string {
  if (typeof value !== 'string' || !value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  // 업무 기준 시각은 서울이다(D-26).
  return parsed.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })
}

export function formatYmd(value: unknown): string {
  if (typeof value !== 'string' || value.length !== 8) return String(value ?? '—')
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`
}
