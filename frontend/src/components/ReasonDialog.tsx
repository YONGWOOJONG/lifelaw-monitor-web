/**
 * 사유 입력 확인 대화상자.
 *
 * 권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §18
 *       DESIGN_admin_screen_inventory_v0_1.md §2 원칙 3·4
 *
 * §18 은 중위험 이상 모든 변경에 **사유**를 요구하고, 고위험 이상에는 실행 전
 * **영향 미리보기**를 요구한다. 그 둘을 한 자리에 모아 모든 쓰기가 같은 관문을
 * 지나게 한다 — 화면마다 다른 확인 방식을 만들면 어떤 경로는 사유 없이
 * 지나가게 된다.
 *
 * 목록 그리드의 인라인 편집을 만들지 않는다는 원칙 3 이 여기서 실질적으로
 * 지켜진다. 쓰기는 전부 이 대화상자를 통과한다.
 */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

/** 서버 DTO 의 `Reason` 최소 길이와 같아야 한다(dto/admin.py REASON_MIN). */
export const REASON_MIN = 5

export function ReasonDialog({
  title,
  impact,
  confirmLabel,
  danger,
  busy,
  error,
  children,
  onCancel,
  onConfirm,
}: {
  title: string
  /** 영향 미리보기. "이 변경으로 N건이 …" 같은 문장을 넣는다(§18). */
  impact?: ReactNode
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  error?: string | null
  /** 추가 입력 필드. 사유 위에 놓인다. */
  children?: ReactNode
  onCancel: () => void
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  const first = useRef<HTMLDivElement>(null)

  // 열리면 첫 입력으로 초점을 옮긴다. 키보드만으로도 닫고 확인할 수 있어야 한다.
  useEffect(() => {
    const node = first.current?.querySelector<HTMLElement>('input, select, textarea')
    node?.focus()
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  const tooShort = reason.trim().length < REASON_MIN

  return (
    <div className="modal-back" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">{title}</div>

        <div className="modal-body" ref={first}>
          {children}

          {impact ? <div className="impact">{impact}</div> : null}

          <label className="field">
            <span>
              사유 <em>필수</em>
            </span>
            <textarea
              value={reason}
              rows={3}
              maxLength={1000}
              placeholder={`왜 이 변경이 필요한지 적습니다 (${REASON_MIN}자 이상). 감사 로그에 남습니다.`}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>

          {error ? <div className="banner banner-error">{error}</div> : null}
        </div>

        <div className="modal-foot">
          <button type="button" onClick={onCancel} disabled={busy}>
            취소
          </button>
          <button
            type="button"
            className={danger ? 'btn-danger' : 'btn-primary'}
            disabled={busy || tooShort}
            onClick={() => onConfirm(reason.trim())}
          >
            {busy ? '처리 중…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

/** 권한·역할 다중 선택. 체크박스를 쓰는 이유는 무엇이 빠졌는지도 보여야 하기 때문이다. */
export function CheckList({
  options,
  selected,
  onToggle,
  labelOf,
}: {
  options: string[]
  selected: string[]
  onToggle: (value: string) => void
  labelOf?: (value: string) => string
}) {
  const chosen = new Set(selected)
  return (
    <div className="checklist">
      {options.map((value) => (
        <label key={value} className={chosen.has(value) ? 'chk is-on' : 'chk'}>
          <input type="checkbox" checked={chosen.has(value)} onChange={() => onToggle(value)} />
          <span>{labelOf ? labelOf(value) : value}</span>
        </label>
      ))}
    </div>
  )
}
