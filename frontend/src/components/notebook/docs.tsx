import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  BarChart3,
  BookOpen,
  ChevronDown,
  ClipboardList,
  Code2,
  Copy,
  Download,
  FileText,
  Folder,
  FolderOpen,
  Lightbulb,
  Link2,
  Maximize2,
  Minimize2,
  Pencil,
  RefreshCw,
  Send,
  Table2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { STAGE_ORDER, STAGE_TITLES } from '../../lib/stages'
import type { FlowStage } from '../../lib/flow'
import { fmtSeconds, jobSeconds, useStageJob } from '../flow/ProcessTimeline'

/* ===================== 文件模型 ===================== */
export interface WbFile {
  key: string
  stage: string
  name: string
  icon: LucideIcon
}
export const FILES: WbFile[] = [
  { key: 'direction', stage: 'direction', name: '研究方向.md', icon: FileText },
  { key: 'literature', stage: 'literature', name: '文献检索与证据.md', icon: BookOpen },
  { key: 'candidates', stage: 'candidates', name: '候选假设.md', icon: Lightbulb },
  { key: 'plan', stage: 'plan', name: '研究方案.md', icon: ClipboardList },
  { key: 'data?tab=assets', stage: 'data', name: '数据集.csv', icon: Table2 },
  { key: 'data?tab=binding', stage: 'data', name: '变量绑定.md', icon: Link2 },
  { key: 'data?tab=results', stage: 'data', name: '检验结果报告.md', icon: BarChart3 },
  { key: 'proposal', stage: 'proposal', name: '研究提案.md', icon: FileText },
]
export const fileOf = (key: string) => FILES.find((f) => f.key === key) || FILES[0]
export function keyOf(stage: string | undefined, search: string) {
  if (!stage) return ''
  if (stage !== 'data') return stage
  const t = new URLSearchParams(search).get('tab')
  return `data?tab=${t === 'binding' || t === 'results' ? t : 'assets'}`
}
export const hrefOf = (id: string, key: string) => (key ? `/p/${id}/${key}` : `/p/${id}`)

/* ===================== 阶段耗时（真实 job 起止） ===================== */
const JOB_KIND: Record<string, string> = {
  literature: 'literature',
  candidates: 'candidates',
  plan: 'plan',
  data: 'analysis',
  proposal: 'proposal',
}
export function useStageJobs(id: string) {
  const r: Record<string, number | undefined> = {}
  const running: Record<string, boolean> = {}
  // 固定顺序调用 hook
  for (const k of Object.keys(JOB_KIND)) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const j = useStageJob(id, JOB_KIND[k])
    r[k] = jobSeconds(j)
    running[k] = !!j && ['queued', 'running'].includes(j.status)
  }
  return { seconds: r, running }
}
export const fmtDur = (s?: number) =>
  s === undefined ? '—' : s < 60 ? fmtSeconds(s) : `${Math.floor(s / 60)}m${Math.round(s % 60)}s`

const STATUS_TEXT: Record<string, string> = {
  locked: '未解锁',
  active: '进行中',
  confirmed: '已确认',
  stale: '需要更新',
}

/* ===================== 操作条 ===================== */
export interface StripActions {
  version: number
  onCopy: () => void
  onExport: () => void
  edit?: { onClick?: () => void; title: string }
  regen?: { onClick?: () => void; title: string }
  fs?: boolean
  onFs?: () => void
  onClose?: () => void
}
export function ActionStrip({ file, a }: { file: WbFile; a: StripActions }) {
  const [menu, setMenu] = useState(false)
  const [msg, setMsg] = useState('')
  const flash = (m: string) => {
    setMsg(m)
    setTimeout(() => setMsg(''), 1600)
  }
  const Icon = file.icon
  return (
    <div className="wb-act">
      <span className="wb-act__fn" title={file.name}>
        <Icon size={14} aria-hidden="true" />
        <span>{msg || file.name}</span>
      </span>
      <span className="wb-act__ver">
        <button
          type="button"
          className="wb-pill"
          title="版本"
          aria-expanded={menu}
          onClick={() => setMenu(!menu)}
        >
          v{a.version} <ChevronDown size={12} aria-hidden="true" />
        </button>
        {menu && (
          <div className="wb-menu" role="menu" onMouseLeave={() => setMenu(false)}>
            {Array.from({ length: a.version }, (_, i) => a.version - i).map((v) => (
              <div key={v} role="menuitem" className={v === a.version ? 'is-on' : ''}>
                v{v}
                {v === a.version ? ' · 当前' : ''}
              </div>
            ))}
            <small>历史版本内容在文档内切换（如提案版本条）</small>
          </div>
        )}
      </span>
      <IconBtn
        title="复制全文"
        onClick={() => {
          a.onCopy()
          flash('已复制')
        }}
      >
        <Copy size={14} />
      </IconBtn>
      <IconBtn title="导出" onClick={a.onExport}>
        <Download size={14} />
      </IconBtn>
      {a.edit && (
        <IconBtn title={a.edit.title} onClick={a.edit.onClick}>
          <Pencil size={14} />
        </IconBtn>
      )}
      {a.regen && (
        <IconBtn title={a.regen.title} onClick={a.regen.onClick}>
          <RefreshCw size={14} />
        </IconBtn>
      )}
      {a.onFs && (
        <IconBtn title={a.fs ? '退出全屏' : '全屏文档'} onClick={a.onFs}>
          {a.fs ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </IconBtn>
      )}
      {a.onClose && (
        <IconBtn title="关闭" onClick={a.onClose}>
          <X size={14} />
        </IconBtn>
      )}
    </div>
  )
}
function IconBtn({
  title,
  onClick,
  children,
}: {
  title: string
  onClick?: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      className="wb-ib"
      title={title}
      aria-label={title}
      disabled={!onClick}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

/* ===================== 全部文件 ===================== */
export function FilesView({
  flow,
  tabs,
  onOpen,
}: {
  flow: FlowStage[]
  tabs: string[]
  onOpen: (k: string) => void
}) {
  const [closed, setClosed] = useState<Record<string, boolean>>({})
  return (
    <div className="wb-files">
      <div className="wb-files__hd">全部文件 · 按阶段</div>
      {STAGE_ORDER.map((st) => {
        const s = flow.find((x) => x.key === st)
        const locked = !s || s.status === 'locked'
        const fs = FILES.filter((f) => f.stage === st)
        const isClosed = closed[st] ?? locked
        return (
          <div key={st}>
            <button
              type="button"
              className="wb-files__grp"
              aria-expanded={!isClosed}
              onClick={() => setClosed({ ...closed, [st]: !isClosed })}
            >
              <ChevronDown size={13} className={isClosed ? 'is-col' : ''} aria-hidden="true" />
              {isClosed ? <Folder size={14} /> : <FolderOpen size={14} />}
              {STAGE_TITLES[st]}
              <small>{locked ? '未解锁' : STATUS_TEXT[s!.status]}</small>
            </button>
            {!isClosed && (
              <div>
                {fs.map((f) => {
                  const Icon = f.icon
                  return (
                    <button
                      key={f.key}
                      type="button"
                      className={`wb-files__file ${tabs.includes(f.key) ? 'is-open' : ''}`}
                      disabled={locked}
                      onClick={() => onOpen(f.key)}
                    >
                      <Icon size={14} aria-hidden="true" />
                      {f.name}
                      {s && s.version > 0 && <small>v{s.version}</small>}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** 导出当前文档：页面文本（非后端文件） */
export function downloadText(name: string, text: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
  a.download = name.replace(/\.(csv|md)$/, '') + '.md'
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
