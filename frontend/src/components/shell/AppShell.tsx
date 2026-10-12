import { useState } from 'react'
import { Link, Outlet, useMatch } from 'react-router-dom'
import { X } from 'lucide-react'
import AppSidebar from './AppSidebar'
import ResearchRail from './ResearchRail'
import { ShellContext, useViewportWide } from './ShellContext'
import { useLlm } from '../../lib/llm'

function ModelBanner() {
  const llm = useLlm()
  const [hidden, setHidden] = useState(() => sessionStorage.getItem('hw-model-banner') === '0')
  if (!llm.data || llm.data.configured || hidden) return null
  return (
    <div className="model-banner" role="status">
      <strong>模型未配置</strong>
      <span>生成类步骤暂不可用；检索、数据与统计检验不受影响。</span>
      <Link to="/settings">前往设置 →</Link>
      <button
        type="button"
        className="model-banner__close"
        aria-label="关闭提示"
        onClick={() => {
          sessionStorage.setItem('hw-model-banner', '0')
          setHidden(true)
        }}
      >
        <X size={14} />
      </button>
    </div>
  )
}

/** 壳层：侧栏（≤1366 默认折叠）+ 主卡（视口高度，页面本身不滚动）+ 右栏（≥1600 常驻，其余抽屉） */
export default function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    const saved = localStorage.getItem('hw-sidebar')
    return saved === null ? window.innerWidth <= 1366 : saved === '1'
  })
  const [railOpen, setRailOpen] = useState(false)
  const [actionsEl, setActionsEl] = useState<HTMLElement | null>(null)
  const wide = useViewportWide(1600)
  const project = useMatch('/p/:id/*')
  const id = project?.params.id
  const toggle = () => {
    localStorage.setItem('hw-sidebar', collapsed ? '0' : '1')
    setCollapsed(!collapsed)
  }
  const showRail = !!id && (wide || railOpen)
  return (
    <ShellContext.Provider
      value={{
        railOpen: showRail,
        toggleRail: () => setRailOpen(!railOpen),
        actionsEl,
        setActionsEl,
      }}
    >
      <div className={`shell ${collapsed ? 'is-collapsed' : ''}`}>
        <a className="skip-link" href="#main-content">
          跳到正文
        </a>
        <AppSidebar collapsed={collapsed} onToggle={toggle} activeProjectId={id} />
        <div className="shell-main">
          <div className={`shell-body ${id && wide ? 'has-rail' : ''}`}>
            <main id="main-content" className="shell-view">
              <ModelBanner />
              <Outlet />
            </main>
            {showRail && (
              <div className={wide ? 'rail-dock' : 'rail-drawer'}>
                {!wide && (
                  <button
                    type="button"
                    className="rail-drawer__close"
                    aria-label="关闭进度与证据"
                    onClick={() => setRailOpen(false)}
                  >
                    <X size={15} />
                  </button>
                )}
                <ResearchRail projectId={id!} />
              </div>
            )}
          </div>
        </div>
      </div>
    </ShellContext.Provider>
  )
}
