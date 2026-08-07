/**
 * API 클라이언트.
 *
 * 권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.4
 *
 * 규칙:
 *  - 세션 쿠키는 HttpOnly 라 JS 가 읽지 못한다. `credentials: 'same-origin'` 으로
 *    브라우저가 붙이게 한다.
 *  - 상태 변경 요청에는 CSRF 토큰을 헤더로 되돌려준다. 쿠키에 담지 않는다.
 *  - **401 과 403 을 구분한다.** 403 을 401 로 오인해 로그인 화면을 띄우면
 *    사용자가 원인을 오해한다(§17.4 강제 조항 5).
 */

export type ApiErrorCode =
  | 'UNAUTHENTICATED'
  | 'INVALID_CREDENTIALS'
  | 'REAUTH_FAILED'
  | 'PERMISSION_DENIED'
  | 'REAUTH_REQUIRED'
  | 'CSRF_FAILED'
  | 'CONTRACT_MISMATCH'
  | 'INTERNAL_ERROR'
  | 'HTTP_ERROR'

export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode
  readonly requiredPermission?: string
  /**
   * 409 낙관적 잠금 충돌이 동봉한 **서버의 현재 값**.
   *
   * 화면은 이걸 받아 사용자가 보던 값과의 차이를 보여주고 다시 결정하게 한다.
   * 조용히 재시도하면 방금 남이 한 변경을 덮어쓴다(§20).
   */
  readonly current?: unknown

  constructor(
    status: number,
    code: ApiErrorCode,
    message: string,
    requiredPermission?: string,
    current?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requiredPermission = requiredPermission
    this.current = current
  }

  get isConflict(): boolean {
    return this.status === 409
  }

  /** 재로그인이 필요한 상태. 권한 부족과 구분한다. */
  get isUnauthenticated(): boolean {
    return this.status === 401
  }

  get isForbidden(): boolean {
    return this.status === 403
  }
}

let csrfToken: string | null = null

export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

export function getCsrfToken(): string | null {
  return csrfToken
}

const STATE_CHANGING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

type QueryValue = string | number | boolean | null | undefined

export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const rendered = search.toString()
  return rendered ? `?${rendered}` : ''
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (STATE_CHANGING.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken

  const response = await fetch(path, {
    method,
    headers,
    // 동일 출처 배포이므로 same-origin 으로 충분하다. include 를 쓰지 않는다.
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const payload: unknown = text ? JSON.parse(text) : null

  if (!response.ok) {
    const body_ = (payload ?? {}) as {
      code?: ApiErrorCode
      message?: string
      detail?: unknown
      required_permission?: string
    }

    // FastAPI 의 `detail` 은 문자열일 수도, 객체일 수도 있다. 409 충돌은 객체로
    // { message, current } 를 담아 보낸다 — 그대로 문자열화하면 화면에
    // "[object Object]" 가 뜬다. 실제로 그렇게 새어나가는 걸 막는 분기다.
    let message = body_.message
    let current: unknown
    const detail = body_.detail
    if (typeof detail === 'string') {
      message ??= detail
    } else if (detail && typeof detail === 'object') {
      const nested = detail as { message?: string; current?: unknown }
      message ??= nested.message
      current = nested.current
    }

    throw new ApiError(
      response.status,
      body_.code ?? 'HTTP_ERROR',
      message ?? `요청이 실패했습니다 (${response.status})`,
      body_.required_permission,
      current,
    )
  }
  return payload as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  // 사유를 본문으로 받아야 하므로 DELETE 에도 body 를 싣는다(§18 사유 필수).
  del: <T>(path: string, body?: unknown) => request<T>('DELETE', path, body),
}
