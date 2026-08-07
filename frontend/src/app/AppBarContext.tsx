/**
 * 앱바 보조 표시 슬롯.
 *
 * 셸이 화면 제목을 갖고, 화면은 오른쪽에 붙일 상태 표시(업무일자, 진행 중인
 * 배치, 갱신 시각)를 넘긴다. 화면마다 헤더를 다시 그리면 같은 정보가 위치를
 * 옮겨 다니게 되므로 자리를 셸이 고정한다.
 *
 * 슬롯 값은 `ReactNode` 다. 진행 중인 배치 표시는 실행 상세로 가는 링크이고
 * (`.running` 은 점이 붙은 알약), 업무일자는 고정폭 `.stamp` 다 — 문자열로는
 * 표현할 수 없어서 노드로 받는다.
 *
 * 매 렌더 새 엘리먼트가 만들어지므로 노드 자체를 effect 의존성에 넣을 수 없다.
 * 그래서 화면이 **무엇이 바뀌면 다시 넣어야 하는지**를 `deps` 로 같이 넘긴다.
 * `deps` 길이는 렌더마다 일정해야 한다(React 의 훅 규칙과 같은 제약이다).
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

interface AppBarValue {
  slot: ReactNode
  setSlot: (slot: ReactNode) => void
}

const AppBarContext = createContext<AppBarValue | null>(null)

export function AppBarProvider({ children }: { children: ReactNode }) {
  const [slot, setSlotState] = useState<ReactNode>(null)

  // **`setSlot` 의 정체성은 영원히 고정이어야 한다.** `useAppBar` 가 이걸 effect
  // 의존성에 넣기 때문이다. slot 이 바뀔 때마다 새 함수를 만들면
  //   set(노드) → slot 변경 → 새 setSlot → effect 재실행 → cleanup(null) → set(노드) → …
  // 로 무한 렌더가 된다(실측: "Maximum update depth exceeded").
  // 노드를 그대로 넘기면 setState 가 갱신 함수로 오해할 여지가 있어 감싼다.
  const setSlot = useCallback((next: ReactNode) => setSlotState(() => next), [])
  const value = useMemo<AppBarValue>(() => ({ slot, setSlot }), [slot, setSlot])

  return <AppBarContext.Provider value={value}>{children}</AppBarContext.Provider>
}

/** 셸이 호출한다. 앱바 오른쪽에 그릴 노드. */
export function useAppBarSlot(): ReactNode {
  return useContext(AppBarContext)?.slot ?? null
}

/** 화면에서 호출한다. 화면을 떠나면 슬롯을 비운다. */
export function useAppBar(slot: ReactNode, deps: readonly unknown[]) {
  const setSlot = useContext(AppBarContext)?.setSlot
  useEffect(() => {
    if (!setSlot) return
    setSlot(slot)
    return () => setSlot(null)
    // slot 은 매 렌더 새 엘리먼트다. 화면이 넘긴 deps 가 갱신 시점을 정한다.
  }, [setSlot, ...deps])
}
