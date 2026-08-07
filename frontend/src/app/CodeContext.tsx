/**
 * 공통 코드 라벨.
 *
 * 권위: DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §14
 *       DESIGN_admin_screen_inventory_v0_1.md S-17
 *
 * **한글 라벨을 프론트엔드에 하드코딩하지 않는다.** 라벨은 서버가 내려준
 * `code_nm` 을 쓴다. `TC_COMMON_CODE` 가 단일 출처이고, 이 앱은 사본을 만들지
 * 않는다.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api } from '../api/client'
import type { CommonCode } from '../api/types'

interface CodeValue {
  codes: CommonCode[]
  /** 코드값 → 표시 라벨. 없으면 코드값 자체를 돌려준다(추측하지 않는다). */
  label: (codeValue: string | null | undefined) => string
  group: (groupCode: string) => CommonCode[]
  loaded: boolean
}

const CodeContext = createContext<CodeValue | null>(null)

export function CodeProvider({ children }: { children: ReactNode }) {
  const [codes, setCodes] = useState<CommonCode[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const result = await api.get<{ items: CommonCode[] }>('/api/codes')
        if (!cancelled) setCodes(result.items)
      } catch {
        // 코드 조회 실패는 화면 전체를 막지 않는다. 라벨이 코드값으로 표시된다.
      } finally {
        if (!cancelled) setLoaded(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const byValue = useMemo(() => {
    const map = new Map<string, string>()
    for (const code of codes) map.set(code.code_val, code.code_nm)
    return map
  }, [codes])

  const label = useCallback(
    (codeValue: string | null | undefined) => {
      if (!codeValue) return '—'
      return byValue.get(codeValue) ?? codeValue
    },
    [byValue],
  )

  const group = useCallback(
    (groupCode: string) => codes.filter((code) => code.code_grp_cd === groupCode),
    [codes],
  )

  const value = useMemo(() => ({ codes, label, group, loaded }), [codes, label, group, loaded])
  return <CodeContext.Provider value={value}>{children}</CodeContext.Provider>
}

export function useCodes(): CodeValue {
  const value = useContext(CodeContext)
  if (!value) throw new Error('CodeProvider 밖에서 useCodes 를 쓸 수 없습니다.')
  return value
}
