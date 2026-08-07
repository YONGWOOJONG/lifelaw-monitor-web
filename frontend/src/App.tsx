/**
 * 앱 셸과 라우팅.
 *
 * 권위: DESIGN_admin_screen_inventory_v0_1.md §5 화면-권한 매트릭스
 *       DESIGN_lifelaw_monitor_web_admin_architecture_v1_2.md §17.3
 *
 * 메뉴는 권한에 따라 숨기지만 **그것은 인가가 아니다.** 서버가 매 요청 검증하며,
 * 숨긴 경로를 주소창으로 직접 열어도 403 이 난다. 그 경우 로그인 화면이 아니라
 * 권한 부족 안내를 보여준다(§17.4 강제 조항 5).
 */

import { useAuth } from './app/AuthContext'
import { CodeProvider } from './app/CodeContext'
import { Link, matchPath, useRouter } from './app/router'
import { DashboardScreen } from './screens/DashboardScreen'
import { LoginScreen } from './screens/LoginScreen'
import {
  BatchRunDetailScreen,
  BatchRunListScreen,
} from './screens/BatchRunScreens'
import {
  CodeScreen,
  ContractStatusScreen,
  LinkScreen,
  SitePolicyScreen,
} from './screens/ReferenceScreens'
import { TargetDetailScreen } from './screens/TargetDetailScreen'
import { TargetListScreen } from './screens/TargetListScreen'

interface NavItem {
  to: string
  label: string
  /** 메뉴 표시 판단에만 쓴다. 서버 인가와 별개다. */
  permission: string
}

const NAV: NavItem[] = [
  { to: '/', label: '운영 현황', permission: 'target:read' },
  { to: '/targets', label: '수집 대상', permission: 'target:read' },
  { to: '/batch-runs', label: '배치 실행', permission: 'batch:read' },
  { to: '/site-policies', label: '사이트 정책', permission: 'policy:read' },
  { to: '/links', label: 'R 마스터', permission: 'target:read' },
  { to: '/codes', label: '공통 코드', permission: 'target:read' },
  { to: '/status', label: '계약 상태', permission: 'batch:read' },
]

function Routes() {
  const { path } = useRouter()

  if (path === '/' || path === '') return <DashboardScreen />
  if (path === '/targets') return <TargetListScreen />
  if (path === '/batch-runs') return <BatchRunListScreen />
  if (path === '/site-policies') return <SitePolicyScreen />
  if (path === '/links') return <LinkScreen />
  if (path === '/codes') return <CodeScreen />
  if (path === '/status') return <ContractStatusScreen />

  const target = matchPath('/targets/:urlId', path)
  if (target) return <TargetDetailScreen urlId={Number(target.urlId)} />

  const run = matchPath('/batch-runs/:runId', path)
  if (run) return <BatchRunDetailScreen runId={Number(run.runId)} />

  return <div className="screen">요청하신 화면을 찾을 수 없습니다.</div>
}

function Shell() {
  const { principal, logout, can } = useAuth()
  const { path } = useRouter()

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">생활법령 모니터링 관리자</div>
        <div className="who">
          <span>
            {principal?.user_nm} <span className="muted">({principal?.roles.join(', ') || '역할 없음'})</span>
          </span>
          <button type="button" onClick={() => void logout()}>
            로그아웃
          </button>
        </div>
      </header>
      <div className="body">
        <nav className="sidebar">
          {NAV.filter((item) => can(item.permission)).map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={path === item.to ? 'nav-item nav-active' : 'nav-item'}
            >
              {item.label}
            </Link>
          ))}
        </nav>
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
      <Shell />
    </CodeProvider>
  )
}
