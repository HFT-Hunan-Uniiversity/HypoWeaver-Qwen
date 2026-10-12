import type { ReactNode } from 'react'

/** 非阶段页（列表、设置、总览）的一行页头 */
export default function PageBar({
  title,
  badge,
  children,
}: {
  title: ReactNode
  badge?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="page-bar no-print">
      <div className="page-bar__title">
        <h1>{title}</h1>
        {badge}
      </div>
      <div className="page-bar__actions">{children}</div>
    </header>
  )
}
