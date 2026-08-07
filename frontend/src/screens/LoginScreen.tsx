/** S-01 로그인. */

import { useState } from 'react'

import { ApiError } from '../api/client'
import { useAuth } from '../app/AuthContext'

export function LoginScreen() {
  const { login } = useAuth()
  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(loginId, password)
    } catch (caught) {
      // 서버는 계정 없음과 비밀번호 불일치를 구분해 주지 않는다. 화면도 그대로 둔다.
      setError(caught instanceof ApiError ? caught.message : '로그인에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>생활법령 모니터링 관리자</h1>
        <label htmlFor="login-id">아이디</label>
        <input
          id="login-id"
          value={loginId}
          onChange={(event) => setLoginId(event.target.value)}
          autoComplete="username"
          required
        />
        <label htmlFor="login-pw">비밀번호</label>
        <input
          id="login-pw"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />
        {error ? <div className="banner banner-error">{error}</div> : null}
        <button type="submit" disabled={busy}>
          {busy ? '확인 중…' : '로그인'}
        </button>
      </form>
    </div>
  )
}
