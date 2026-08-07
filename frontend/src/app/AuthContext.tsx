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
      setPrincipal(await api.get<Principal>('/api/auth/me'))
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
    await api.post<void>('/api/auth/reauth', { password })
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
