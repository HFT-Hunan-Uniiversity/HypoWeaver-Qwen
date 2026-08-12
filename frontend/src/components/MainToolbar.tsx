/**
 * MainToolbar：主卡内 48px 细工具条（原 AppHeader 退役后由它接管）。
 * 左：移动端侧栏开关 + 当前视图标题；右：视图相关操作（由调用方注入）。
 */
import { PanelLeft } from 'lucide-react'
import type { ReactNode } from 'react'

interface MainToolbarProps {
  title: string
  subtitle?: string
  onToggleSidebar: () => void
  children?: ReactNode
}

export function MainToolbar({ title, subtitle, onToggleSidebar, children }: MainToolbarProps) {
  return (
    <header className="main-toolbar">
      <button type="button" className="main-toolbar__menu" aria-label="切换侧边栏" onClick={onToggleSidebar}>
        <PanelLeft size={16} />
      </button>
      <span className="main-toolbar__sep" aria-hidden="true" />
      <div className="main-toolbar__title">
        <strong>{title}</strong>
        {subtitle && <small>{subtitle}</small>}
      </div>
      <div className="main-toolbar__actions">{children}</div>
    </header>
  )
}
