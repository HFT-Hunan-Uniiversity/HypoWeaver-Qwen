import { useState } from 'react'
import { Link, Outlet, useMatch } from 'react-router-dom'
import { Settings2, X } from 'lucide-react'
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

/** 壳层：项目页由 StageLayout 渲染「研究手记」时间线；项目列表 / 设置为简洁页头 + 整页滚动。 */
export default function AppShell() {
  const [actionsEl, setActionsEl] = useState<HTMLElement | null>(null)
  const project = useMatch('/p/:id/*')
  return (
    <ShellContext.Provider
      value={{ railOpen: false, toggleRail: () => {}, actionsEl, setActionsEl }}
    >
      <a className="skip-link" href="#main-content">
        跳到正文
      </a>
      {project ? (
        <main id="main-content" className="nb-page">
          <Outlet />
        </main>
      ) : (
        <div className="nb-plain">
          <header className="nb-hero is-plain">
            <Link to="/" className="nb-logo" title="HypoWeaver · 分步向导">
              HW
            </Link>
            <div className="nb-hero__txt">
              <h1>HypoWeaver</h1>
              <p>实证科研工作台</p>
            </div>
            <Link to="/" className="nb-small">
              项目
            </Link>
            <Link to="/settings" className="nb-small is-icon" title="设置" aria-label="设置">
              <Settings2 size={14} />
            </Link>
          </header>
          <main id="main-content">
            <ModelBanner />
            <Outlet />
          </main>
        </div>
      )}
    </ShellContext.Provider>
  )
}
