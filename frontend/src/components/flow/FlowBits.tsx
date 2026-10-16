import { useState, type ReactNode } from 'react'
import { Check, X } from 'lucide-react'
import ProcessTimeline, { type TimelineStep } from './ProcessTimeline'
import type { CheckItem } from './FlowContext'

/** 任务清单：最多 3 项，单动作阶段不显示 */
export function StepChecklist({ items }: { items?: CheckItem[] }) {
  if (!items || items.length < 2) return null
  const now = items.findIndex((i) => !i.done)
  return (
    <ol className="flow-checklist" aria-label="本阶段任务">
      {items.slice(0, 3).map((it, i) => (
        <li key={it.label} className={it.done ? 'is-done' : i === now ? 'is-now' : ''}>
          {it.done ? <Check size={12} aria-hidden="true" /> : <span>{i + 1}</span>}
          {it.label}
        </li>
      ))}
    </ol>
  )
}

/** 系统长时间工作时的进度：ClawsGO 式过程时间线（每步一行，当前步加粗转圈） */
export function ProgressView({
  title,
  detail,
  steps,
}: {
  title: string
  detail?: string
  steps?: { label: string; state: 'done' | 'now' | 'todo' | 'failed' | 'na' }[]
}) {
  let list: TimelineStep[] = (
    steps?.length ? steps : [{ label: title, state: 'now' as const }]
  ).map((st, i) => ({ key: `${i}-${st.label}`, label: st.label, state: st.state }))
  if (!list.some((x) => x.state === 'now')) {
    const i = list.findIndex((x) => x.state === 'todo')
    if (i >= 0) list = list.map((x, j) => (j === i ? { ...x, state: 'now' as const } : x))
  }
  return (
    <section className="flow-progress-tl" role="status" aria-live="polite">
      <ProcessTimeline title={title} steps={list} />
      <p className="muted">{detail || '完成后会自动显示结果，你可以先离开此页。'}</p>
    </section>
  )
}

/** 空状态：这里会出现什么 + 示例 + 让它出现的按钮 */
export function EmptyState({
  title,
  what,
  example,
  action,
  blocked,
  children,
}: {
  title: string
  what: ReactNode
  example?: { title: string; body: string }
  action?: { label: string; onClick: () => void; disabled?: boolean }
  /** 无法执行时的提示（例如模型未配置），替代按钮 */
  blocked?: string
  children?: ReactNode
}) {
  return (
    <section className="flow-empty fill">
      <h2>{title}</h2>
      <p>{what}</p>
      {example && (
        <div className="flow-empty__example" aria-label="示例">
          <small>示例</small>
          <strong>{example.title}</strong>
          <span>{example.body}</span>
        </div>
      )}
      {children}
      {blocked ? (
        <p className="muted">{blocked}</p>
      ) : (
        action && (
          <button
            type="button"
            className="product-button is-primary-soft"
            disabled={action.disabled}
            onClick={action.onClick}
          >
            {action.label}
          </button>
        )
      )}
    </section>
  )
}

const introKey = (k: string) => `hw.intro.${k}`
export function useIntro(stage: string) {
  const [open, setOpen] = useState(() => !localStorage.getItem(introKey(stage)))
  const [cur, setCur] = useState(stage)
  if (cur !== stage) {
    setCur(stage)
    setOpen(!localStorage.getItem(introKey(stage)))
  }
  return {
    open,
    show: () => setOpen(true),
    dismiss: () => {
      localStorage.setItem(introKey(stage), '1')
      setOpen(false)
    },
  }
}

export function IntroCard({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <div className="flow-intro" role="note">
      <strong>这一阶段做什么</strong>
      <span>{text}</span>
      <button type="button" className="icon-button" aria-label="知道了，关闭说明" onClick={onClose}>
        <X size={14} />
      </button>
    </div>
  )
}
