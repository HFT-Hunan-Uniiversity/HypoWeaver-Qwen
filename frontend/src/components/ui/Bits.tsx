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

/** 从结果对象取生成模型名：统一读顶层 llm_model（兼容旧记录的 generated_by.model）。
 * 注意：不读 obj.model —— 方案的 model 是统计模型设定。 */
export function llmModelOf(obj: unknown): string | undefined {
  if (!obj || typeof obj !== 'object') return undefined
  const o = obj as { llm_model?: unknown; generated_by?: { model?: unknown } }
  for (const v of [o.llm_model, o.generated_by?.model]) if (typeof v === 'string' && v) return v
  return undefined
}

/** “由 <model> 生成”；传 of= 结果对象或 model= 字符串 */
export function GeneratedBy({ model: m, of }: { model?: string | null; of?: unknown }) {
  const model = m || llmModelOf(of)
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
    return <span className="needs-model is-ok">模型 · {llm.data.llm_model}</span>
  return (
    <Link className="needs-model" to="/settings" title="此操作需要模型，点击前往设置">
      需要模型
    </Link>
  )
}

export function StatusBadge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`status-badge is-${tone}`}>{children}</span>
}
