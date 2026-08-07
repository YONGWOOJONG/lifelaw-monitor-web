/**
 * 앱 셸과 라우팅.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md §5 화면-권한 매트릭스
 *       DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3
 *
 * 메뉴는 권한에 따라 숨기지만 **그것은 인가가 아니다.** 서버가 매 요청 검증하며,
 * 숨긴 경로를 주소창으로 직접 열어도 403 이 난다. 그 경우 로그인 화면이 아니라
 * 권한 부족 안내를 보여준다(§17.4 강제 조항 5).
 *
 * 2a 시안: 남색 상단바를 없애고 전체 높이 좌측 레일로 옮겼다. 화면 제목과
 * 배치 상태는 각 화면이 아니라 셸의 앱바가 갖는다 — 어느 화면에 있든 지금
 * 어떤 배치가 도는지 같은 자리에 보이게 하기 위해서다. 앱바 오른쪽 내용은
 * 화면이 `useAppBar` 로 넘긴다. 메뉴 그룹은 표시용 묶음일 뿐 권한 계층이 아니다.
 */

import { AppBarProvider, useAppBarSlot } from './app/AppBarContext'
import { useAuth } from './app/AuthContext'
import { CodeProvider } from './app/CodeContext'
import { Link, matchPath, useRouter } from './app/router'
import { DashboardScreen } from './screens/DashboardScreen'
import { LoginScreen } from './screens/LoginScreen'
import { BatchRunDetailScreen, BatchRunListScreen } from './screens/BatchRunScreens'
import {
  CodeScreen,
  ContractStatusScreen,
  LinkScreen,
  SitePolicyScreen,
} from './screens/ReferenceScreens'
import { AuditScreen } from './screens/AuditScreen'
import { RoleScreen } from './screens/RoleScreen'
import { TargetDetailScreen } from './screens/TargetDetailScreen'
import { TargetListScreen } from './screens/TargetListScreen'
import { UserScreen } from './screens/UserScreen'

interface NavItem {
  to: string
  label: string
  /** 표시용 묶음. 인가와 무관하다. */
  group: string
  /** 메뉴 표시 판단에만 쓴다. 서버 인가와 별개다. */
  permission: string
}

const NAV: NavItem[] = [
  { to: '/', label: '운영 현황', group: '운영', permission: 'target:read' },
  { to: '/targets', label: '수집 대상', group: '운영', permission: 'target:read' },
  { to: '/batch-runs', label: '배치 실행', group: '운영', permission: 'batch:read' },
  { to: '/site-policies', label: '사이트 정책', group: '기준정보', permission: 'policy:read' },
  { to: '/links', label: 'R 마스터', group: '기준정보', permission: 'target:read' },
  { to: '/codes', label: '공통 코드', group: '기준정보', permission: 'target:read' },
  { to: '/status', label: '계약 상태', group: '기준정보', permission: 'batch:read' },
  // 관리 묶음은 서로 다른 권한을 쓴다. 감사 열람은 계정 관리와 분리돼 있어
  // (설계 §5 직무 분리) ADMIN 에게는 감사 메뉴가, AUDITOR 에게는 사용자 메뉴가
  // 보이지 않는다. 메뉴 노출은 표시일 뿐이며 인가는 서버가 한다.
  { to: '/users', label: '사용자', group: '관리', permission: 'user:manage' },
  { to: '/roles', label: '역할·권한', group: '관리', permission: 'user:manage' },
  { to: '/audit', label: '감사 로그', group: '관리', permission: 'audit:read' },
]

/** 앱바에 띄울 화면 제목. 라우팅 판단이 아니라 표시 전용이다. */
function titleOf(path: string): string {
  const exact = NAV.find((item) => item.to === path)
  if (exact) return exact.label
  if (matchPath('/targets/:urlId', path)) return '수집 대상 상세'
  if (matchPath('/batch-runs/:runId', path)) return '배치 실행 상세'
  return '생활법령 모니터링'
}

function Routes() {
  const { path } = useRouter()

  if (path === '/' || path === '') return <DashboardScreen />
  if (path === '/targets') return <TargetListScreen />
  if (path === '/batch-runs') return <BatchRunListScreen />
  if (path === '/site-policies') return <SitePolicyScreen />
  if (path === '/links') return <LinkScreen />
  if (path === '/codes') return <CodeScreen />
  if (path === '/status') return <ContractStatusScreen />
  if (path === '/users') return <UserScreen />
  if (path === '/roles') return <RoleScreen />
  if (path === '/audit') return <AuditScreen />

  const target = matchPath('/targets/:urlId', path)
  if (target) return <TargetDetailScreen urlId={Number(target.urlId)} />

  const run = matchPath('/batch-runs/:runId', path)
  if (run) return <BatchRunDetailScreen runId={Number(run.runId)} />

  return <div className="screen">요청하신 화면을 찾을 수 없습니다.</div>
}

function Rail() {
  const { principal, logout, can } = useAuth()
  const { path } = useRouter()

  const visible = NAV.filter((item) => can(item.permission))
  const groups = visible.reduce<{ name: string; items: NavItem[] }[]>((acc, item) => {
    const last = acc[acc.length - 1]
    if (last && last.name === item.group) last.items.push(item)
    else acc.push({ name: item.group, items: [item] })
    return acc
  }, [])

  return (
    <nav className="rail">
      <div className="rail-head">
        <div className="rail-brand">생활법령 모니터링</div>
        <div className="rail-sub">관리자 콘솔</div>
      </div>
      <div className="rail-nav">
        {groups.map((group) => (
          <div key={group.name} className="rail-section">
            <div className="rail-group">{group.name}</div>
            {group.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={path === item.to ? 'nav-item nav-active' : 'nav-item'}
              >
                {item.label}
              </Link>
            ))}
          </div>
        ))}
      </div>
      <div className="rail-foot">
        <div>
          <div className="who">{principal?.user_nm}</div>
          <div className="roles">{principal?.roles.join(', ') || '역할 없음'}</div>
        </div>
        <button type="button" onClick={() => void logout()}>
          로그아웃
        </button>
      </div>
    </nav>
  )
}

function Shell() {
  const { path } = useRouter()
  const meta = useAppBarSlot()

  return (
    <div className="shell">
      <Rail />
      <div className="main">
        <header className="appbar">
          <div className="appbar-left">
            <h2>{titleOf(path)}</h2>
          </div>
          <div className="appbar-right">{meta}</div>
        </header>
        <main className="content">
          <Routes />
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const { principal, loading } = useAuth()

  if (loading) return <div className="muted pad">확인 중…</div>
  if (!principal) return <LoginScreen />

  return (
    <CodeProvider>
      <AppBarProvider>
        <Shell />
      </AppBarProvider>
    </CodeProvider>
  )
}
