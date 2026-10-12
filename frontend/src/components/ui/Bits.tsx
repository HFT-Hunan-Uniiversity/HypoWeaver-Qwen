import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { useLlm } from '../../lib/llm'

export interface VersionItem {
  id: string
  label: string
  note?: string
  tone?: 'stale' | 'failed' | 'ok'
}

/** 分段胶囊：替代原生 <select> 的版本切换 */
export function VersionPills({
  label,
  items,
  value,
  onChange,
}: {
  label: string
  items: VersionItem[]
  value: string
  onChange: (id: string) => void
}) {
  return (
    <div className="version-pills" role="radiogroup" aria-label={label}>
      <span className="version-pills__label">{label}</span>
      {items.map((it) => (
        <button
          type="button"
          role="radio"
          aria-checked={it.id === value}
          key={it.id}
          className={`${it.id === value ? 'is-active' : ''} ${it.tone ? 'is-' + it.tone : ''}`}
          onClick={() => onChange(it.id)}
          title={it.note}
        >
          {it.label}
          {it.note && <small>{it.note}</small>}
        </button>
      ))}
    </div>
  )
}

/** “由 <model> 生成” */
export function GeneratedBy({ model }: { model?: string | null }) {
  if (!model) return null
  return (
    <span className="generated-by">
      <Sparkles size={12} aria-hidden="true" />由 {model} 生成
    </span>
  )
}

/** 需要模型的按钮旁的标记；未配置时给出去设置的入口 */
export function NeedsModel() {
  const llm = useLlm()
  if (llm.data?.configured)
    return <span className="needs-model is-ok">模型 · {llm.data.model}</span>
  return (
    <Link className="needs-model" to="/settings" title="此操作需要模型，点击前往设置">
      需要模型
    </Link>
  )
}

export function StatusBadge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`status-badge is-${tone}`}>{children}</span>
}
