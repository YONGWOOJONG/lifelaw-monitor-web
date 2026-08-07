/**
 * 재인증 관문.
 *
 * 권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §18
 *       DESIGN_admin_screen_inventory_v0_1.md S-02 재인증
 *
 * §18 은 최고 위험 작업(계정 권한 변경 등)에 **재인증**을 요구한다. 서버는
 * `PERMISSIONS_REQUIRING_REAUTH` 로 이미 그것을 강제하고, 신선하지 않으면
 * `REAUTH_REQUIRED` 로 403 을 낸다.
 *
 * 그 403 을 화면이 그냥 배너로 보여주면 **막다른 길**이 된다 — 사용자가
 * "비밀번호를 다시 확인해 주세요"를 읽어도 확인할 수단이 없다. 실제로 그랬다.
 * 그래서 이 관문이 403 을 잡아 비밀번호를 받고, 성공하면 **원래 하려던 작업을
 * 그대로 다시 실행한다.** 사용자는 같은 버튼을 두 번 누르지 않는다.
 *
 * 재인증은 로그인과 다르다 — 세션을 새로 만들지 않고 신선도만 갱신한다.
 */

import { useCallback, useRef, useState } from 'react'

import { ApiError } from '../api/client'
import { useAuth } from '../app/AuthContext'

export function useReauthGate() {
  const { reauth } = useAuth()
  const [asking, setAsking] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 재인증 후 다시 실행할 작업. ref 인 이유는 대화상자 렌더와 무관하게
  // 마지막 시도를 그대로 붙들고 있어야 하기 때문이다.
  const pending = useRef<(() => Promise<void>) | null>(null)

  /**
   * `action` 을 실행하고, REAUTH_REQUIRED 면 비밀번호를 물은 뒤 다시 실행한다.
   * 그 외 오류는 호출자에게 그대로 던진다 — 여기서 삼키면 화면이 조용히 실패한다.
   */
  const guard = useCallback(async (action: () => Promise<void>) => {
    try {
      await action()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REAUTH_REQUIRED') {
        pending.current = action
        setPassword('')
        setError(null)
        setAsking(true)
        return
      }
      throw err
    }
  }, [])

  const submit = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      await reauth(password)
      const action = pending.current
      pending.current = null
      setAsking(false)
      setPassword('')
      if (action) await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }, [password, reauth])

  const cancel = useCallback(() => {
    pending.current = null
    setAsking(false)
    setPassword('')
    setError(null)
  }, [])

  const prompt = asking ? (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && cancel()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="재인증">
        <div className="modal-head">재인증</div>
        <div className="modal-body">
          <p className="muted">
            최고 위험 작업입니다. 계속하려면 <strong>본인 비밀번호</strong>를 다시 입력하세요.
            확인되면 방금 요청한 작업이 이어서 실행됩니다.
          </p>
          <label className="field">
            <span>비밀번호</span>
            {/* eslint-disable-next-line jsx-a11y/no-autofocus -- 관문이 열리면 여기가 유일한 입력이다 */}
            <input
              type="password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && password) void submit()
              }}
            />
          </label>
          {error ? <div className="banner banner-error">{error}</div> : null}
        </div>
        <div className="modal-foot">
          <button type="button" onClick={cancel} disabled={busy}>
            취소
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !password}
            onClick={() => void submit()}
          >
            {busy ? '확인 중…' : '확인'}
          </button>
        </div>
      </div>
    </div>
  ) : null

  return { guard, prompt }
}
