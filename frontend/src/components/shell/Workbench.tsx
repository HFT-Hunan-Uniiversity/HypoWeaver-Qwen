import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
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
  LayoutDashboard,
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
  { key: '', stage: '', name: '项目总览', icon: LayoutDashboard },
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

/** 标签页：按项目存于 sessionStorage */
export function useTabs(id: string, current: string) {
  const sk = `hw.tabs.${id}`
  const [tabs, setTabs] = useState<string[]>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(sk) || '[]')
    } catch {
      return []
    }
  })
  useEffect(() => {
    setTabs((t) => (t.includes(current) ? t : [...t, current]))
  }, [current]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => sessionStorage.setItem(sk, JSON.stringify(tabs)), [sk, tabs])
  const uniq = Array.from(new Set(tabs))
  const list = uniq.includes(current) ? uniq : [...uniq, current]
  return [list, setTabs] as const
}

/* ===================== 阶段耗时（真实 job 起止） ===================== */
const JOB_KIND: Record<string, string> = {
  literature: 'literature',
  candidates: 'candidates',
  plan: 'plan',
  data: 'analysis',
  proposal: 'proposal',
}
export function useStageSeconds(id: string): Record<string, number | undefined> {
  const r: Record<string, number | undefined> = {}
  // 固定顺序调用 hook
  for (const k of Object.keys(JOB_KIND)) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const j = useStageJob(id, JOB_KIND[k])
    r[k] = jobSeconds(j)
  }
  return r
}
const fmtDur = (s?: number) =>
  s === undefined ? '—' : s < 60 ? fmtSeconds(s) : `${Math.floor(s / 60)}m${Math.round(s % 60)}s`

const STATUS_TEXT: Record<string, string> = {
  locked: '未解锁',
  active: '进行中',
  confirmed: '已确认',
  stale: '需要更新',
}

/* ===================== 进度点计划 ===================== */
export function PlanDots({
  flow,
  currentStage,
  seconds,
  onOpen,
}: {
  flow: FlowStage[]
  currentStage?: string
  seconds: Record<string, number | undefined>
  onOpen: (stage: string) => void
}) {
  const [tip, setTip] = useState<{ k: string; x: number; y: number } | null>(null)
  const done = flow.filter((s) => s.status === 'confirmed').length
  const cur = flow.find((s) => s.key === currentStage) || flow.find((s) => s.status !== 'confirmed')
  const known = Object.values(seconds).filter((x): x is number => x !== undefined)
  const total = known.length ? known.reduce((a, b) => a + b, 0) : undefined
  const t = tip && flow.find((s) => s.key === tip.k)
  return (
    <div className="wb-plan">
      <span className="wb-dots" role="list" aria-label="六阶段进度">
        {flow.map((s) => (
          <button
            key={s.key}
            type="button"
            role="listitem"
            className={`wb-dot is-${s.status} ${s.key === cur?.key ? 'is-cur' : ''}`}
            aria-label={`${STAGE_TITLES[s.key]} · ${STATUS_TEXT[s.status]}`}
            onMouseEnter={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              setTip({ k: s.key, x: r.left, y: r.top })
            }}
            onMouseLeave={() => setTip(null)}
            onFocus={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              setTip({ k: s.key, x: r.left, y: r.top })
            }}
            onBlur={() => setTip(null)}
            onClick={() => {
              setTip(null)
              onOpen(s.key)
            }}
          />
        ))}
      </span>
      {cur && (
        <span
          className="wb-plan__lab"
          title={total !== undefined ? `已记录任务用时合计 ${fmtDur(total)}` : undefined}
        >
          {STAGE_TITLES[cur.key]} <em className={`is-${cur.status}`}>{STATUS_TEXT[cur.status]}</em>
          <small> {done}/6</small>
        </span>
      )}
      {t && tip && (
        <div
          className="wb-tip"
          role="tooltip"
          style={{ left: Math.max(6, tip.x - 20), top: tip.y - 10 }}
        >
          <b>{STAGE_TITLES[t.key]}</b>{' '}
          <span className="m">
            · {STATUS_TEXT[t.status]} ·{' '}
            {t.key === 'direction' ? '无后台任务' : fmtDur(seconds[t.key])}
          </span>
          {t.summary && <div>{t.summary}</div>}
          <div className="m">
            {t.status === 'locked'
              ? '尚未解锁'
              : `点击打开 ${t.key === 'data' ? '检验结果报告.md' : FILES.find((f) => f.stage === t.key)?.name}`}
          </div>
        </div>
      )}
    </div>
  )
}

/* ===================== 操作条 ===================== */
export interface StripActions {
  version: number
  onCopy: () => void
  onExport: () => void
  edit?: { onClick?: () => void; title: string }
  regen?: { onClick?: () => void; title: string }
  fs: boolean
  onFs: () => void
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
      <IconBtn title={a.edit?.title || '修改'} onClick={a.edit?.onClick}>
        <Pencil size={14} />
      </IconBtn>
      <IconBtn title={a.regen?.title || '重新生成'} onClick={a.regen?.onClick}>
        <RefreshCw size={14} />
      </IconBtn>
      <IconBtn title={a.fs ? '退出全屏' : '全屏文档'} onClick={a.onFs}>
        {a.fs ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </IconBtn>
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

/* ===================== 左栏：对话 ===================== */
export function ChatPane({
  title,
  direction,
  flow,
  banner,
  plan,
  strip,
}: {
  title: string
  direction: string
  flow: FlowStage[]
  banner?: ReactNode
  plan: ReactNode
  strip: ReactNode
}) {
  const done = flow.filter((s) => s.status === 'confirmed').length
  return (
    <section className="wb-chat no-print" aria-label="对话">
      <header className="wb-chat__hd" title={title}>
        {title}
      </header>
      {banner}
      <div className="wb-chat__msgs">
        {direction && <div className="wb-msg wb-msg--user">{direction}</div>}
        <div className="wb-msg wb-msg--sys">
          <div className="wb-msg__who">
            <i>HW</i>系统进度记录 <span className="wb-tag">非 AI 回复</span>
          </div>
          <p>
            六个阶段已确认 {done} 个。
            {flow
              .filter((s) => s.status !== 'locked')
              .map((s) => `${STAGE_TITLES[s.key]}：${STATUS_TEXT[s.status]}`)
              .join('；')}
            。
          </p>
          <p>右侧打开的是各阶段的文档；确认、修改等操作在文档顶部。</p>
        </div>
      </div>
      <div className="wb-chat__foot">
        {plan}
        {strip}
        <div className="wb-composer">
          <textarea
            disabled
            rows={2}
            aria-label="对话输入（示意，未接入）"
            placeholder="对话功能尚未接入后端（示意）"
          />
          <div className="wb-composer__row">
            <span className="wb-tag">示意</span>
            <span className="wb-grow" />
            <button type="button" className="wb-send" disabled aria-label="发送（未接入）">
              <Send size={14} />
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ===================== 标签页 ===================== */
export function TabBar({
  tabs,
  active,
  files,
  onOpen,
  onClose,
  onFiles,
  onExitFs,
}: {
  onExitFs?: () => void
  tabs: string[]
  active: string | null
  files: boolean
  onOpen: (k: string) => void
  onClose: (k: string) => void
  onFiles: () => void
}) {
  return (
    <div className="wb-tabs no-print">
      <div className="wb-tabs__list" role="tablist" aria-label="已打开的文件">
        {tabs.map((k) => {
          const f = fileOf(k)
          const Icon = f.icon
          return (
            <div
              key={k || 'overview'}
              role="tab"
              tabIndex={0}
              aria-selected={!files && k === active}
              className={`wb-tab ${!files && k === active ? 'is-on' : ''}`}
              title={f.name}
              onClick={() => onOpen(k)}
              onKeyDown={(e) => e.key === 'Enter' && onOpen(k)}
            >
              <Icon size={13} aria-hidden="true" />
              <span className="wb-tab__nm">{f.name}</span>
              <button
                type="button"
                className="wb-tab__x"
                aria-label={`关闭 ${f.name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  onClose(k)
                }}
              >
                <X size={11} />
              </button>
            </div>
          )
        })}
      </div>
      {onExitFs && (
        <button type="button" className="wb-allbtn" onClick={onExitFs}>
          <Minimize2 size={13} aria-hidden="true" /> 退出全屏
        </button>
      )}
      <button
        type="button"
        className={`wb-allbtn ${files ? 'is-on' : ''}`}
        aria-pressed={files}
        onClick={onFiles}
      >
        <Folder size={13} aria-hidden="true" /> 全部文件
      </button>
    </div>
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
                {st === 'data' && (
                  <span className="wb-files__file is-mock" title="后端暂无回归代码接口">
                    <Code2 size={14} aria-hidden="true" />
                    main_regression.py
                    <small>示意 · 暂无接口</small>
                  </span>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ===================== 文档左侧目录（自动从标题生成） ===================== */
export function DocToc({ deps }: { deps: unknown }) {
  const [items, setItems] = useState<{ el: HTMLElement; text: string; lvl: number }[]>([])
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => {
    const body = document.querySelector('.stage-body')
    if (!body) return
    const scan = () => {
      const hs = Array.from(body.querySelectorAll<HTMLElement>('h2, h3')).filter(
        (h) =>
          h.offsetParent &&
          h.textContent?.trim() &&
          !h.closest('[role="dialog"], details:not([open])'),
      )
      setItems(
        hs
          .slice(0, 24)
          .map((el) => ({ el, text: el.textContent!.trim(), lvl: el.tagName === 'H3' ? 2 : 1 })),
      )
    }
    scan()
    const mo = new MutationObserver(() => {
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(scan, 250)
    })
    mo.observe(body, { childList: true, subtree: true })
    return () => {
      mo.disconnect()
      window.clearTimeout(timer.current)
    }
  }, [deps])
  if (items.length < 2) return null
  return (
    <nav className="wb-toc no-print" aria-label="文档目录">
      {items.map((it, i) => (
        <button
          key={i}
          type="button"
          className={`wb-toc__i lvl-${it.lvl}`}
          title={it.text}
          onClick={() => it.el.scrollIntoView({ block: 'start', behavior: 'smooth' })}
        >
          {it.text}
        </button>
      ))}
    </nav>
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

export function useOpenStage(id: string) {
  const navigate = useNavigate()
  return (stage: string) => {
    const f = stage === 'data' ? 'data?tab=results' : stage
    navigate(hrefOf(id, f))
  }
}
