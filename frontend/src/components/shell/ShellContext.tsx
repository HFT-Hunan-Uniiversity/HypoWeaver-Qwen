import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface ShellState {
  railOpen: boolean
  toggleRail: () => void
  /** 页头右侧主操作挂载点（由 StageLayout / PageBar 提供） */
  actionsEl: HTMLElement | null
  setActionsEl: (el: HTMLElement | null) => void
}

export const ShellContext = createContext<ShellState>({
  railOpen: false,
  toggleRail: () => {},
  actionsEl: null,
  setActionsEl: () => {},
})

export const useShell = () => useContext(ShellContext)

/** 页面把主操作按钮渲染进页头右侧（一行页头，去掉卡片内重复标题） */
export function StageActions({ children }: { children: ReactNode }) {
  const { actionsEl } = useShell()
  return actionsEl ? createPortal(children, actionsEl) : null
}

/** 局部滚动区：一屏布局中唯一允许滚动的区域 */
export function ScrollRegion({
  children,
  className = '',
  label,
}: {
  children: ReactNode
  className?: string
  label?: string
}) {
  return (
    <div
      className={`scroll-region ${className}`}
      data-scroll-region=""
      aria-label={label}
      tabIndex={0}
    >
      {children}
    </div>
  )
}

export function useViewportWide(min: number) {
  const [wide, setWide] = useState(() => window.innerWidth >= min)
  useEffect(() => {
    const on = () => setWide(window.innerWidth >= min)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [min])
  return wide
}
