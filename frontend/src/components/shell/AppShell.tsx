import { useState } from 'react'
import { Link, Outlet, useLocation, useMatch } from 'react-router-dom'
import { Menu, PanelRight } from 'lucide-react'
import AppSidebar from './AppSidebar'
import ResearchRail from './ResearchRail'
import { useLlm } from '../../lib/llm'
import { STAGE_TITLES, stageKeyFromPath, useOverview } from '../../lib/stages'

function ModelBanner() {
  const llm = useLlm()
  if (!llm.data || llm.data.configured) return null
  return (
    <div className="model-banner" role="status">
      <strong>模型未配置</strong>
      <span>生成检索式、候选、方案、解读与提案需要千问模型；检索、数据与统计检验不受影响。</span>
      <Link to="/settings">前往设置 →</Link>
    </div>
  )
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('hw-sidebar') === '1')
  const [drawer, setDrawer] = useState(false)
  const [rail, setRail] = useState(false)
  const project = useMatch('/p/:id/*')
  const id = project?.params.id
  const { pathname } = useLocation()
  const overview = useOverview(id)
  const stage = stageKeyFromPath(pathname)
  const toggle = () => {
    localStorage.setItem('hw-sidebar', collapsed ? '0' : '1')
    setCollapsed(!collapsed)
  }
  const isOverview = !!id && !stage
  return (
    <div
      className={`shell ${collapsed ? 'is-collapsed' : ''} ${drawer ? 'is-drawer-open' : ''}`}
      onClick={() => drawer && setDrawer(false)}
    >
      <a className="skip-link" href="#main-content">
        跳到正文
      </a>
      <AppSidebar collapsed={collapsed} onToggle={toggle} activeProjectId={id} />
      <div className="shell-main">
        <div className="main-toolbar no-print">
          <button
            type="button"
            className="main-toolbar__menu"
            aria-label="打开侧边栏"
            onClick={(e) => {
              e.stopPropagation()
              setDrawer(true)
            }}
          >
            <Menu size={16} />
          </button>
          <div className="main-toolbar__title">
            <strong>{id ? overview.data?.project.title || '研究项目' : 'HypoWeaver'}</strong>
            <small>{stage ? STAGE_TITLES[stage] : id ? '项目总览' : '实证科研工作台'}</small>
          </div>
          {id && !isOverview && (
            <div className="main-toolbar__actions">
              <button
                type="button"
                className="quiet-button rail-toggle"
                aria-pressed={rail}
                onClick={() => setRail(!rail)}
              >
                <PanelRight size={14} aria-hidden="true" />
                进度与证据
              </button>
            </div>
          )}
        </div>
        <ModelBanner />
        <div
          className={`shell-body ${id ? 'has-rail' : ''} ${rail || isOverview ? 'rail-open' : ''}`}
        >
          <main id="main-content" className="shell-view--scroll">
            <Outlet />
          </main>
          {id && <ResearchRail projectId={id} />}
        </div>
      </div>
    </div>
  )
}
