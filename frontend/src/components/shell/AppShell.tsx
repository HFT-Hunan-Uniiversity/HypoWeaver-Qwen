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

/** 壳层：项目内 StageLayout；首页统一工作台壳层；设置页共用向导顶栏（.wz-top）。 */
export default function AppShell() {
  const [actionsEl, setActionsEl] = useState<HTMLElement | null>(null)
  const project = useMatch('/p/:id/*')
  const home = useMatch({ path: '/', end: true })
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
      ) : home ? (
        <main
          id="main-content"
          style={{ height: '100%', minHeight: '100vh', margin: 0, padding: 0 }}
        >
          <Outlet />
        </main>
      ) : (
        <div className="wz nb-plain">
          <header className="wz-top">
            <div className="wz-top__row">
              <Link to="/" className="nb-logo hw-mark" title="HypoWeaver · 返回工作台首页">
                <img className="hw-mark__img" src="/brand/hw-logo.svg" alt="" draggable={false} />
              </Link>
              <Link to="/" className="wz-top__crumb">
                HypoWeaver 工作台
              </Link>
              <span className="wz-top__sep" aria-hidden="true">
                /
              </span>
              <h1>服务与用量设置</h1>
              <Link to="/" className="nb-small">
                ← 返回工作台
              </Link>
              <Link to="/?view=projects" className="nb-small">
                我的项目
              </Link>
            </div>
          </header>
          <ModelBanner />
          <main id="main-content" className="wz-main">
            <Outlet />
          </main>
        </div>
      )}
    </ShellContext.Provider>
  )
}
