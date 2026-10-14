import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { Link, Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom'
import { PanelLeft, Plus, Search, Settings2, X } from 'lucide-react'
import AppSidebar from './AppSidebar'
import { ShellContext } from './ShellContext'
import { useLlm } from '../../lib/llm'

export function ModelBanner() {
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

/** 壳层：最左图标栏（HW / 项目抽屉 / 搜索 / 新建 / 设置）+ 主区。
 *  项目路由下主区由 StageLayout 渲染为「左 AI 对话 + 右文档」工作台；其余页面为单栏整页滚动。 */
export default function AppShell() {
  const [drawer, setDrawer] = useState<false | 'list' | 'search'>(false)
  const [q, setQ] = useState('')
  const [actionsEl, setActionsEl] = useState<HTMLElement | null>(null)
  const project = useMatch('/p/:id/*')
  const id = project?.params.id
  const navigate = useNavigate()
  const { pathname } = useLocation()
  useEffect(() => setDrawer(false), [pathname])
  return (
    <ShellContext.Provider
      value={{ railOpen: false, toggleRail: () => {}, actionsEl, setActionsEl }}
    >
      <div className={`shell is-wb ${id ? 'is-project' : ''}`}>
        <a className="skip-link" href="#main-content">
          跳到正文
        </a>
        <nav className="wb-rail no-print" aria-label="全局">
          <Link to="/" className="wb-rail__logo" title="HypoWeaver · 研究项目">
            HW
          </Link>
          <button
            type="button"
            className={`wb-rail__btn ${drawer === 'list' ? 'is-on' : ''}`}
            title="项目列表"
            aria-label="项目列表"
            aria-expanded={drawer === 'list'}
            onClick={() => setDrawer(drawer ? false : 'list')}
          >
            <PanelLeft size={16} />
          </button>
          <button
            type="button"
            className="wb-rail__btn"
            title="搜索项目（打开项目列表）"
            aria-label="搜索项目"
            onClick={() => setDrawer(drawer === 'search' ? false : 'search')}
          >
            <Search size={16} />
          </button>
          <button
            type="button"
            className="wb-rail__btn"
            title="新建研究"
            aria-label="新建研究"
            onClick={() => navigate('/?new=1')}
          >
            <Plus size={16} />
          </button>
          <span className="wb-rail__grow" />
          <Link to="/settings" className="wb-rail__btn" title="设置" aria-label="设置">
            <Settings2 size={16} />
          </Link>
        </nav>
        {drawer && (
          <>
            <div className="wb-drawer-mask" onClick={() => setDrawer(false)} />
            <div className="wb-drawer">
              {drawer === 'search' && (
                <input
                  autoFocus
                  className="wb-drawer__search"
                  placeholder="按标题搜索项目"
                  aria-label="按标题搜索项目"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              )}
              <AppSidebar
                filter={drawer === 'search' ? q : ''}
                collapsed={false}
                onToggle={() => setDrawer(false)}
                activeProjectId={id}
              />
            </div>
          </>
        )}
        <div className="shell-main">
          {id ? (
            <Outlet />
          ) : (
            <main id="main-content" className="shell-view">
              <ModelBanner />
              <Outlet />
              <ScrollFab />
            </main>
          )}
        </div>
      </div>
    </ShellContext.Provider>
  )
}

/** 整页滚动的回到顶部/底部按钮：滚过一屏后出现，靠近底部时指向顶部 */
export function ScrollFab() {
  const [state, setState] = useState<'none' | 'up' | 'down'>('none')
  useEffect(() => {
    const el = document.querySelector<HTMLElement>('.shell-view')
    if (!el) return
    const on = () => {
      const max = el.scrollHeight - el.clientHeight
      if (max < 200) return setState('none')
      setState(el.scrollTop > max / 2 ? 'up' : 'down')
    }
    on()
    el.addEventListener('scroll', on, { passive: true })
    const ro = new ResizeObserver(on)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild)
    return () => {
      el.removeEventListener('scroll', on)
      ro.disconnect()
    }
  }, [])
  if (state === 'none') return null
  const go = () => {
    const el = document.querySelector<HTMLElement>('.shell-view')
    if (!el) return
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollTo({ top: state === 'up' ? 0 : el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }
  return (
    <button
      type="button"
      className="scroll-fab no-print"
      aria-label={state === 'up' ? '回到顶部' : '到底部'}
      title={state === 'up' ? '回到顶部' : '到底部'}
      onClick={go}
    >
      {state === 'up' ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
    </button>
  )
}
