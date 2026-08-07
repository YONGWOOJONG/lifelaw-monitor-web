/**
 * 최소 라우터.
 *
 * react-router 를 쓰지 않는다. 2026-08-07 시점 최신판(7.18.2)이 GHSA-qwww-vcr4-c8h2
 * (RSC 모드 CSRF 우회, high) 취약 범위 안이고 패치 버전이 없다. 이 앱의 라우팅은
 * 평면 경로 8개뿐이라 History API 로 충분하며, 의존성과 함께 취약점도 제거된다.
 *
 * 지원하는 것: 정적 경로, `:param` 한 단계, 뒤로가기.
 * 지원하지 않는 것: 중첩 라우트, 데이터 로더, 스크롤 복원.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

interface RouterValue {
  path: string
  navigate: (to: string, options?: { replace?: boolean }) => void
}

const RouterContext = createContext<RouterValue | null>(null)

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(() => window.location.pathname)

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    if (options?.replace) window.history.replaceState({}, '', to)
    else window.history.pushState({}, '', to)
    setPath(to)
  }, [])

  const value = useMemo(() => ({ path, navigate }), [path, navigate])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext)
  if (!value) throw new Error('RouterProvider 밖에서 useRouter 를 쓸 수 없습니다.')
  return value
}

/** `/targets/:urlId` 같은 패턴을 현재 경로와 맞춰본다. */
export function matchPath(pattern: string, path: string): Record<string, string> | null {
  const patternParts = pattern.split('/').filter(Boolean)
  const pathParts = path.split('/').filter(Boolean)
  if (patternParts.length !== pathParts.length) return null

  const params: Record<string, string> = {}
  for (let i = 0; i < patternParts.length; i += 1) {
    const expected = patternParts[i]
    const actual = pathParts[i]
    if (expected.startsWith(':')) {
      params[expected.slice(1)] = decodeURIComponent(actual)
    } else if (expected !== actual) {
      return null
    }
  }
  return params
}

export function Link({
  to,
  children,
  className,
}: {
  to: string
  children: ReactNode
  className?: string
}) {
  const { navigate } = useRouter()
  return (
    <a
      href={to}
      className={className}
      onClick={(event) => {
        // 새 탭 열기 같은 브라우저 기본 동작은 막지 않는다.
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
        event.preventDefault()
        navigate(to)
      }}
    >
      {children}
    </a>
  )
}
