/**
 * 최소 라우터.
 *
 * react-router 를 쓰지 않는다. 2026-08-07 시점 최신판(7.18.2)이 GHSA-qwww-vcr4-c8h2
 * (RSC 모드 CSRF 우회, high) 취약 범위 안이고 패치 버전이 없다. 이 앱의 라우팅은
 * 평면 경로 8개뿐이라 History API 로 충분하며, 의존성과 함께 취약점도 제거된다.
 *
 * 지원하는 것: 정적 경로, `:param` 한 단계, 쿼리스트링, 뒤로가기.
 * 지원하지 않는 것: 중첩 라우트, 데이터 로더, 스크롤 복원.
 *
 * **`path` 에는 쿼리스트링이 절대 섞이지 않는다.** 라우팅 판단은 `path === '/targets'`
 * 같은 정확 비교라, 한 번이라도 `?...` 가 붙으면 그 화면은 통째로 not-found 가 된다.
 * 실제로 그런 적이 있다 — 대시보드 알림 카드 네 개가 전부 "화면을 찾을 수 없습니다"
 * 로 떨어졌고, `popstate` 는 `pathname` 을 쓰는 탓에 새로고침하면 멀쩡해서 눈에
 * 잘 띄지 않았다. 그래서 여기서 한 번만 쪼개고, 화면은 `search` 로만 질의를 읽는다.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

interface RouterValue {
  /** 경로만. 쿼리스트링 없음. */
  path: string
  /** `?` 를 포함한 쿼리스트링. 없으면 빈 문자열. */
  search: string
  navigate: (to: string, options?: { replace?: boolean }) => void
}

const RouterContext = createContext<RouterValue | null>(null)

/** 주소 한 줄을 경로와 쿼리로 쪼갠다. 해시는 쓰지 않으므로 버린다. */
function split(url: string): { path: string; search: string } {
  const withoutHash = url.split('#')[0]
  const cut = withoutHash.indexOf('?')
  if (cut < 0) return { path: withoutHash, search: '' }
  return { path: withoutHash.slice(0, cut), search: withoutHash.slice(cut) }
}

function current(): { path: string; search: string } {
  return { path: window.location.pathname, search: window.location.search }
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState(current)

  useEffect(() => {
    const onPop = () => setLocation(current())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    if (options?.replace) window.history.replaceState({}, '', to)
    else window.history.pushState({}, '', to)
    setLocation(split(to))
  }, [])

  const value = useMemo(
    () => ({ path: location.path, search: location.search, navigate }),
    [location.path, location.search, navigate],
  )
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext)
  if (!value) throw new Error('RouterProvider 밖에서 useRouter 를 쓸 수 없습니다.')
  return value
}

/** 현재 쿼리스트링. 화면이 진입 조건(어떤 필터로 들어왔는지)을 읽을 때 쓴다. */
export function useSearchParams(): URLSearchParams {
  const { search } = useRouter()
  return useMemo(() => new URLSearchParams(search), [search])
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
