/**
 * S-18 사용자 관리.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-18 (C·R·U, 위험 최고)
 *       DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §7.2 §18 §20
 *
 * **삭제 버튼이 없다.** §7.2 가 "삭제는 비활성화로 대체"로 규정했다. 계정을
 * 지우면 감사 로그의 `actor` 가 가리키는 사람이 사라진다.
 *
 * 잠금 사고 방어는 서버가 한다 — 자기 자신 비활성화, 자기 관리권한 제거,
 * 마지막 관리자 제거. 화면은 그 거부 메시지를 그대로 보여준다. 버튼을 숨겨
 * 막는 방식을 쓰지 않는 이유는 그것이 인가가 아니기 때문이다(§17.3).
 */

import { useCallback, useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import { useReauthGate } from '../components/ReauthGate'
import { CheckList, ReasonDialog } from '../components/ReasonDialog'
import { ErrorBanner, Loading, formatInstant } from '../components/common'

interface User {
  user_id: number
  login_id: string
  user_nm: string
  use_yn: string
  last_login_at: string | null
  failed_login_cnt: number
  locked_until: string | null
  roles: string[]
}

interface Role {
  role_cd: string
  role_nm: string
}

type Dialog =
  | { kind: 'create' }
  | { kind: 'rename'; user: User }
  | { kind: 'roles'; user: User }
  | { kind: 'active'; user: User }
  | { kind: 'password'; user: User }
  | { kind: 'unlock'; user: User }
  | null

export function UserScreen() {
  const [users, setUsers] = useState<User[] | null>(null)
  const [roles, setRoles] = useState<Role[]>([])
  const [error, setError] = useState<unknown>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState(false)
  const [dialogError, setDialogError] = useState<string | null>(null)

  const [loginId, setLoginId] = useState('')
  const [userNm, setUserNm] = useState('')
  const [password, setPassword] = useState('')
  const [picked, setPicked] = useState<string[]>([])

  const { guard, prompt } = useReauthGate()

  // 목록 조회조차 user:manage 라 재인증에 걸린다. 그래서 읽기도 관문을 지난다.
  const load = useCallback(() => {
    void guard(async () => {
      const [u, r] = await Promise.all([
        api.get<{ items: User[] }>('/api/admin/users'),
        api.get<{ items: Role[] }>('/api/admin/roles'),
      ])
      setUsers(u.items)
      setRoles(r.items)
      setError(null)
    }).catch(setError)
  }, [guard])

  useEffect(load, [load])

  const open = (next: Dialog) => {
    setDialogError(null)
    if (next?.kind === 'create') {
      setLoginId('')
      setUserNm('')
      setPassword('')
      setPicked([])
    } else if (next?.kind === 'rename') {
      setUserNm(next.user.user_nm)
    } else if (next?.kind === 'roles') {
      setPicked(next.user.roles)
    } else if (next?.kind === 'password') {
      setPassword('')
    }
    setDialog(next)
  }

  const run = async (call: () => Promise<{ items: User[] }>) => {
    setBusy(true)
    setDialogError(null)
    try {
      await guard(async () => {
        const result = await call()
        setUsers(result.items)
        setDialog(null)
      })
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) {
        setDialogError(`${err.message} 목록을 새로 읽었습니다.`)
        load()
      } else {
        setDialogError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      setBusy(false)
    }
  }

  const toggle = (value: string) =>
    setPicked((current) =>
      current.includes(value) ? current.filter((v) => v !== value) : [...current, value],
    )

  const labelOf = (role_cd: string) => {
    const found = roles.find((r) => r.role_cd === role_cd)
    return found ? `${found.role_nm} · ${role_cd}` : role_cd
  }

  const isLocked = (user: User) =>
    Boolean(user.locked_until && new Date(user.locked_until).getTime() > Date.now())

  // **관문 대화상자는 이 조기 반환에도 함께 렌더해야 한다.** 목록 조회 자체가
  // 재인증에 걸리므로 첫 진입은 항상 로딩 상태이고, 여기서 prompt 를 빼면
  // "불러오는 중…"에서 영원히 멈춘다(실측으로 잡았다).
  if (error)
    return (
      <div className="screen">
        <ErrorBanner error={error} />
        {prompt}
      </div>
    )
  if (!users)
    return (
      <div className="screen">
        <Loading what="사용자 목록을" />
        {prompt}
      </div>
    )

  return (
    <div className="screen">
      <div className="section-head">
        <h2>사용자</h2>
        <button type="button" className="btn-primary" onClick={() => open({ kind: 'create' })}>
          사용자 추가
        </button>
      </div>

      <p className="muted">
        계정은 삭제하지 않고 비활성화합니다. 비활성화와 비밀번호 재설정은 해당 사용자의 세션을
        즉시 끊습니다.
      </p>

      <div className="panel">
        <table className="grid">
          <thead>
            <tr>
              <th>사용자</th>
              <th>역할</th>
              <th>상태</th>
              <th>마지막 로그인</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.user_id} className={user.use_yn === 'N' ? 'is-off' : undefined}>
                <td>
                  <div className="row-date">{user.user_nm}</div>
                  <div className="row-sub">
                    {user.login_id} · #{user.user_id}
                  </div>
                </td>
                <td>
                  <div className="perm-tags">
                    {user.roles.length === 0 ? (
                      <span className="muted">역할 없음</span>
                    ) : (
                      user.roles.map((role) => (
                        <span key={role} className="tag" title={labelOf(role)}>
                          {role}
                        </span>
                      ))
                    )}
                  </div>
                </td>
                <td>
                  {user.use_yn === 'Y' ? (
                    <span className="badge badge-ok">활성</span>
                  ) : (
                    <span className="badge">비활성</span>
                  )}
                  {isLocked(user) ? <span className="badge badge-warn">잠김</span> : null}
                  {user.failed_login_cnt > 0 ? (
                    <span className="row-sub">실패 {user.failed_login_cnt}회</span>
                  ) : null}
                </td>
                <td className="muted">
                  {user.last_login_at ? formatInstant(user.last_login_at) : '—'}
                </td>
                <td className="cell-actions">
                  <button type="button" onClick={() => open({ kind: 'rename', user })}>
                    이름
                  </button>
                  <button type="button" onClick={() => open({ kind: 'roles', user })}>
                    역할
                  </button>
                  <button type="button" onClick={() => open({ kind: 'password', user })}>
                    비밀번호
                  </button>
                  {isLocked(user) || user.failed_login_cnt > 0 ? (
                    <button type="button" onClick={() => open({ kind: 'unlock', user })}>
                      잠금 해제
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className={user.use_yn === 'Y' ? 'btn-danger' : undefined}
                    onClick={() => open({ kind: 'active', user })}
                  >
                    {user.use_yn === 'Y' ? '비활성화' : '활성화'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog?.kind === 'create' ? (
        <ReasonDialog
          title="사용자 추가"
          confirmLabel="추가"
          busy={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.post('/api/admin/users', {
                login_id: loginId,
                user_nm: userNm,
                password,
                roles: picked,
                reason,
              }),
            )
          }
        >
          <label className="field">
            <span>로그인 ID</span>
            <input value={loginId} maxLength={100} onChange={(e) => setLoginId(e.target.value)} />
          </label>
          <label className="field">
            <span>이름</span>
            <input value={userNm} maxLength={100} onChange={(e) => setUserNm(e.target.value)} />
          </label>
          <label className="field">
            <span>초기 비밀번호</span>
            <input
              type="password"
              value={password}
              maxLength={200}
              placeholder="8자 이상"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <div className="field">
            <span>역할</span>
            <CheckList
              options={roles.map((r) => r.role_cd)}
              selected={picked}
              onToggle={toggle}
              labelOf={labelOf}
            />
          </div>
        </ReasonDialog>
      ) : null}

      {dialog?.kind === 'rename' ? (
        <ReasonDialog
          title={`이름 변경 — ${dialog.user.login_id}`}
          confirmLabel="저장"
          busy={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.put(`/api/admin/users/${dialog.user.user_id}`, { user_nm: userNm, reason }),
            )
          }
        >
          <label className="field">
            <span>이름</span>
            <input value={userNm} maxLength={100} onChange={(e) => setUserNm(e.target.value)} />
          </label>
        </ReasonDialog>
      ) : null}

      {dialog?.kind === 'roles' ? (
        <ReasonDialog
          title={`역할 변경 — ${dialog.user.login_id}`}
          confirmLabel="저장"
          busy={busy}
          error={dialogError}
          impact={<>계정 권한 변경은 최고 위험 작업입니다. 다음 로그인부터가 아니라 즉시 적용됩니다.</>}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.put(`/api/admin/users/${dialog.user.user_id}/roles`, {
                roles: picked,
                reason,
                expected_roles: dialog.user.roles,
              }),
            )
          }
        >
          <div className="field">
            <span>역할</span>
            <CheckList
              options={roles.map((r) => r.role_cd)}
              selected={picked}
              onToggle={toggle}
              labelOf={labelOf}
            />
          </div>
        </ReasonDialog>
      ) : null}

      {dialog?.kind === 'password' ? (
        <ReasonDialog
          title={`비밀번호 재설정 — ${dialog.user.login_id}`}
          confirmLabel="재설정"
          busy={busy}
          error={dialogError}
          impact={<>이 사용자의 모든 세션이 끊기고 로그인 실패 잠금도 함께 풀립니다.</>}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.put(`/api/admin/users/${dialog.user.user_id}/password`, { password, reason }),
            )
          }
        >
          <label className="field">
            <span>새 비밀번호</span>
            <input
              type="password"
              value={password}
              maxLength={200}
              placeholder="8자 이상"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
        </ReasonDialog>
      ) : null}

      {dialog?.kind === 'unlock' ? (
        <ReasonDialog
          title={`잠금 해제 — ${dialog.user.login_id}`}
          confirmLabel="해제"
          busy={busy}
          error={dialogError}
          impact={<>실패 횟수 {dialog.user.failed_login_cnt}회가 0으로 초기화됩니다. 비밀번호는 그대로입니다.</>}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() => api.put(`/api/admin/users/${dialog.user.user_id}/unlock`, { reason }))
          }
        />
      ) : null}

      {dialog?.kind === 'active' ? (
        <ReasonDialog
          title={`${dialog.user.use_yn === 'Y' ? '비활성화' : '활성화'} — ${dialog.user.login_id}`}
          confirmLabel={dialog.user.use_yn === 'Y' ? '비활성화' : '활성화'}
          danger={dialog.user.use_yn === 'Y'}
          busy={busy}
          error={dialogError}
          impact={
            dialog.user.use_yn === 'Y' ? (
              <>이 사용자의 세션이 즉시 끊기고 로그인할 수 없게 됩니다. 계정은 삭제되지 않습니다.</>
            ) : (
              <>이 사용자가 다시 로그인할 수 있게 됩니다. 역할은 그대로 유지됩니다.</>
            )
          }
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.put(`/api/admin/users/${dialog.user.user_id}/active`, {
                active: dialog.user.use_yn !== 'Y',
                reason,
              }),
            )
          }
        />
      ) : null}
      {prompt}
    </div>
  )
}
