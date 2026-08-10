/**
 * 인증 상태.
 *
 * 권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3 §17.4
 *
 * `permissions` 는 **메뉴 표시용**이다. 이 값으로 접근을 허용하지 않는다.
 * 서버가 매 요청 검증하며, 프론트가 숨긴 메뉴를 직접 호출해도 403 이 난다.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, api, setCsrfToken } from '../api/client'
import type { LoginResponse, Principal } from '../api/types'

interface AuthValue {
  principal: Principal | null
  loading: boolean
  login: (loginId: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /**
   * 비밀번호 재확인. 최고 위험 작업은 세션 재사용이 아니라 재인증을 요구한다(§18).
   * 성공하면 서버 세션의 `reauth_at` 이 갱신되어 몇 분간 유효하다.
   */
  reauth: (password: string) => Promise<void>
  refresh: () => Promise<void>
  /** 메뉴 표시 판단에만 쓴다. 인가가 아니다. */
  can: (permission: string) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<Principal>('/api/auth/me')
      // **새로고침 복구의 핵심.** CSRF 토큰은 메모리에만 있어서 새로고침하면
      // 사라지는데 세션 쿠키는 남는다. 그러면 로그인 상태로 보이지만 모든
      // 쓰기가 CSRF_FAILED 로 막히고, 재인증도 POST 라 풀 수가 없었다.
      // 서버가 세션에서 토큰을 다시 계산해 내려주므로 여기서 되살린다.
      setCsrfToken(me.csrf_token)
      setPrincipal(me)
    } catch (error) {
      // 401 은 "아직 로그인하지 않음"이다. 오류로 표시하지 않는다.
      if (error instanceof ApiError && error.isUnauthenticated) setPrincipal(null)
      else throw error
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(async (loginId: string, password: string) => {
    const result = await api.post<LoginResponse>('/api/auth/login', {
      login_id: loginId,
      password,
    })
    setCsrfToken(result.csrf_token)
    setPrincipal(result.principal)
  }, [])

  const reauth = useCallback(async (password: string) => {
    // 응답도 Principal 이므로 토큰이 함께 온다. 재인증 성공 뒤 이어서 실행되는
    // 쓰기 요청이 확실히 유효한 토큰을 쓰게 갱신해 둔다.
    const refreshed = await api.post<Principal>('/api/auth/reauth', { password })
    setCsrfToken(refreshed.csrf_token)
    setPrincipal(refreshed)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post<void>('/api/auth/logout')
    } finally {
      // 서버 호출이 실패해도 클라이언트 상태는 비운다.
      setCsrfToken(null)
      setPrincipal(null)
    }
  }, [])

  const can = useCallback(
    (permission: string) => principal?.permissions.includes(permission) ?? false,
    [principal],
  )

  const value = useMemo(
    () => ({ principal, loading, login, logout, reauth, refresh, can }),
    [principal, loading, login, logout, reauth, refresh, can],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider 밖에서 useAuth 를 쓸 수 없습니다.')
  return value
}
