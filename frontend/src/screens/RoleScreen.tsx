/**
 * S-19 역할·권한 관리.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md S-19 (C·R·U·D, 위험 최고)
 *       DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17 §18 §20
 *
 * 이 저장소에서 **진짜 삭제가 있는 유일한 화면**이다. 그래서 삭제 버튼 옆에
 * 항상 사용자 수가 붙어 있고, 시스템 역할은 버튼 자체가 잠긴다. 다만 그 잠금은
 * 표시일 뿐이며 인가가 아니다 — 서버가 매 요청 다시 막는다(§17.3).
 *
 * 수정 요청에는 사용자가 **보고 있던 값**을 함께 보낸다. 그 사이 남이 바꿨으면
 * 409 가 오고, 조용히 재시도하지 않고 차이를 보여준다(§20).
 */

import { useCallback, useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import { useReauthGate } from '../components/ReauthGate'
import { CheckList, ReasonDialog } from '../components/ReasonDialog'
import { ErrorBanner, Loading } from '../components/common'

interface Role {
  role_cd: string
  role_nm: string
  role_desc: string | null
  sort_ord: number
  permissions: string[]
  user_cnt: number
  is_system: boolean
}

interface Permission {
  perm_cd: string
  perm_nm: string
}

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; role: Role }
  | { kind: 'delete'; role: Role }
  | null

export function RoleScreen() {
  const [roles, setRoles] = useState<Role[] | null>(null)
  const [perms, setPerms] = useState<Permission[]>([])
  const [error, setError] = useState<unknown>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState(false)
  const [dialogError, setDialogError] = useState<string | null>(null)

  // 대화상자 안에서 편집 중인 값
  const [roleCd, setRoleCd] = useState('')
  const [roleNm, setRoleNm] = useState('')
  const [roleDesc, setRoleDesc] = useState('')
  const [picked, setPicked] = useState<string[]>([])

  const { guard, prompt } = useReauthGate()

  // 목록 조회조차 user:manage 라 재인증에 걸린다. 그래서 읽기도 관문을 지난다.
  const load = useCallback(() => {
    void guard(async () => {
      const [r, p] = await Promise.all([
        api.get<{ items: Role[] }>('/api/admin/roles'),
        api.get<{ items: Permission[] }>('/api/admin/permissions'),
      ])
      setRoles(r.items)
      setPerms(p.items)
      setError(null)
    }).catch(setError)
  }, [guard])

  useEffect(load, [load])

  const open = (next: Dialog) => {
    setDialogError(null)
    if (next?.kind === 'create') {
      setRoleCd('')
      setRoleNm('')
      setRoleDesc('')
      setPicked([])
    } else if (next?.kind === 'edit') {
      setRoleCd(next.role.role_cd)
      setRoleNm(next.role.role_nm)
      setRoleDesc(next.role.role_desc ?? '')
      setPicked(next.role.permissions)
    }
    setDialog(next)
  }

  const run = async (call: () => Promise<{ items: Role[] }>) => {
    setBusy(true)
    setDialogError(null)
    try {
      await guard(async () => {
        const result = await call()
        setRoles(result.items)
        setDialog(null)
      })
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) {
        // 409 는 남이 먼저 바꿨다는 뜻이다. 목록을 서버 값으로 되돌려
        // 사용자가 무엇이 달라졌는지 보고 다시 결정하게 한다.
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

  const labelOf = (perm_cd: string) => {
    const found = perms.find((p) => p.perm_cd === perm_cd)
    return found ? `${found.perm_nm} · ${perm_cd}` : perm_cd
  }

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
  if (!roles)
    return (
      <div className="screen">
        <Loading what="역할 목록을" />
        {prompt}
      </div>
    )

  return (
    <div className="screen">
      <div className="screen-head">
        <h2>역할·권한</h2>
        <button type="button" className="btn-primary" onClick={() => open({ kind: 'create' })}>
          역할 추가
        </button>
      </div>

      <p className="muted">
        권한 자체는 코드가 검사하는 상수이므로 여기서 만들지 않습니다. 역할과 매핑만 바꿉니다.
        모든 변경에는 사유가 필요하고 감사 로그에 남습니다.
      </p>

      <div className="panel">
        <table className="grid">
          <thead>
            <tr>
              <th>역할</th>
              <th>설명</th>
              <th>권한</th>
              <th>사용자</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => (
              <tr key={role.role_cd}>
                <td>
                  <div className="row-date">{role.role_nm}</div>
                  <div className="row-sub">
                    {role.role_cd}
                    {role.is_system ? <span className="badge">시스템</span> : null}
                  </div>
                </td>
                <td className="muted">{role.role_desc ?? '—'}</td>
                <td>
                  <div className="perm-tags">
                    {role.permissions.length === 0 ? (
                      <span className="muted">없음</span>
                    ) : (
                      role.permissions.map((perm) => (
                        <span key={perm} className="tag" title={labelOf(perm)}>
                          {perm}
                        </span>
                      ))
                    )}
                  </div>
                </td>
                <td>{role.user_cnt.toLocaleString('ko-KR')}명</td>
                <td className="cell-actions">
                  <button type="button" onClick={() => open({ kind: 'edit', role })}>
                    수정
                  </button>
                  <button
                    type="button"
                    className="btn-danger"
                    disabled={role.is_system || role.user_cnt > 0}
                    title={
                      role.is_system
                        ? '시스템 역할은 삭제할 수 없습니다'
                        : role.user_cnt > 0
                          ? '이 역할을 쓰는 사용자가 있습니다'
                          : undefined
                    }
                    onClick={() => open({ kind: 'delete', role })}
                  >
                    삭제
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog?.kind === 'create' ? (
        <ReasonDialog
          title="역할 추가"
          confirmLabel="추가"
          busy={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.post('/api/admin/roles', {
                role_cd: roleCd,
                role_nm: roleNm,
                role_desc: roleDesc || null,
                permissions: picked,
                reason,
              }),
            )
          }
        >
          <label className="field">
            <span>역할 코드</span>
            <input
              value={roleCd}
              maxLength={30}
              placeholder="예: REPORT_VIEWER"
              onChange={(event) => setRoleCd(event.target.value.toUpperCase())}
            />
          </label>
          <label className="field">
            <span>역할 이름</span>
            <input value={roleNm} maxLength={100} onChange={(e) => setRoleNm(e.target.value)} />
          </label>
          <label className="field">
            <span>설명</span>
            <input value={roleDesc} maxLength={500} onChange={(e) => setRoleDesc(e.target.value)} />
          </label>
          <div className="field">
            <span>권한</span>
            <CheckList
              options={perms.map((p) => p.perm_cd)}
              selected={picked}
              onToggle={toggle}
              labelOf={labelOf}
            />
          </div>
        </ReasonDialog>
      ) : null}

      {dialog?.kind === 'edit' ? (
        <ReasonDialog
          title={`역할 수정 — ${dialog.role.role_cd}`}
          confirmLabel="저장"
          busy={busy}
          error={dialogError}
          impact={
            dialog.role.user_cnt > 0 ? (
              <>
                이 역할을 쓰는 사용자 <strong>{dialog.role.user_cnt}명</strong>의 권한이 즉시
                바뀝니다.
              </>
            ) : null
          }
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.put(`/api/admin/roles/${encodeURIComponent(dialog.role.role_cd)}`, {
                role_nm: roleNm,
                role_desc: roleDesc || null,
                permissions: picked,
                reason,
                // 사용자가 화면을 열 때 본 값. 그 사이 바뀌면 서버가 409 로 막는다.
                expected_role_nm: dialog.role.role_nm,
                expected_permissions: dialog.role.permissions,
              }),
            )
          }
        >
          <label className="field">
            <span>역할 이름</span>
            <input value={roleNm} maxLength={100} onChange={(e) => setRoleNm(e.target.value)} />
          </label>
          <label className="field">
            <span>설명</span>
            <input value={roleDesc} maxLength={500} onChange={(e) => setRoleDesc(e.target.value)} />
          </label>
          <div className="field">
            <span>권한</span>
            <CheckList
              options={perms.map((p) => p.perm_cd)}
              selected={picked}
              onToggle={toggle}
              labelOf={labelOf}
            />
          </div>
        </ReasonDialog>
      ) : null}

      {dialog?.kind === 'delete' ? (
        <ReasonDialog
          title={`역할 삭제 — ${dialog.role.role_cd}`}
          confirmLabel="삭제"
          danger
          busy={busy}
          error={dialogError}
          impact={
            <>
              <strong>{dialog.role.role_nm}</strong> 역할과 권한 매핑{' '}
              {dialog.role.permissions.length}건이 삭제됩니다. 이 작업은 되돌릴 수 없습니다.
            </>
          }
          onCancel={() => setDialog(null)}
          onConfirm={(reason) =>
            void run(() =>
              api.del(`/api/admin/roles/${encodeURIComponent(dialog.role.role_cd)}`, { reason }),
            )
          }
        />
      ) : null}
      {prompt}
    </div>
  )
}
