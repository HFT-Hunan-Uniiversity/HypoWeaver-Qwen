import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  ChevronDown,
  Folder,
  Loader2,
  Lock,
  Pencil,
  Settings2,
} from 'lucide-react'
import { STAGE_TITLES, stageKeyFromPath, useOverview } from '../../lib/stages'
import { useLlm } from '../../lib/llm'
import {
  dotState,
  downstreamCount,
  FLOW_ORDER,
  type FlowStage,
  type StageKey,
} from '../../lib/flow'
import { FlowProvider, ReaderCtx, useFlow, type PrimarySpec } from '../flow/FlowContext'
import { StepChecklist } from '../flow/FlowBits'
import { ModelBanner } from './AppShell'
import {
  ActionStrip,
  FILES,
  FilesView,
  downloadText,
  fileOf,
  fmtDur,
  useStageJobs,
} from '../notebook/docs'

const PAGES: Record<StageKey, ReturnType<typeof lazy>> = {
  direction: lazy(() => import('../../pages/Direction')),
  literature: lazy(() => import('../../pages/Literature')),
  candidates: lazy(() => import('../../pages/Candidates')),
  plan: lazy(() => import('../../pages/Plan')),
  data: lazy(() => import('../../pages/Data')),
  proposal: lazy(() => import('../../pages/Proposal')),
}
const STATUS_TEXT: Record<string, string> = {
  locked: '未解锁',
  active: '进行中',
  running: '运行中',
  confirmed: '已确认',
  stale: '上游已改，需重新确认',
}
const loading = <p className="loading-line">正在加载…</p>

/** 研究手记：sticky hero + 居中单列六阶段时间线。只有整页滚动。 */
export default function StageLayout() {
  const { id } = useParams()
  const overview = useOverview(id)
  if (!overview.data) return <p className="loading-line">正在读取项目…</p>
  return (
    <FlowProvider projectId={id!} stages={overview.data.stages}>
      <Notebook title={overview.data.project.title} />
    </FlowProvider>
  )
}

function Notebook({ title }: { title: string }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { projectId: id, flow } = useFlow()
  const routeKey = stageKeyFromPath(pathname) as StageKey | undefined
  const firstOpen = flow.find((s) => s.status !== 'confirmed' && s.status !== 'locked')
  const [open, setOpen] = useState<StageKey | null>(
    (routeKey && flow.find((x) => x.key === routeKey)?.status !== 'locked' ? routeKey : null) ||
      firstOpen?.key ||
      null,
  )
  const [reader, setReader] = useState<null | { kind: 'files' } | { kind: 'doc'; key: string }>(
    null,
  )
  const { seconds, running } = useStageJobs(id)
  const runOf = (k: StageKey) => (k === 'data' ? running.data : running[k]) || false
  const heroRef = useRef<HTMLElement>(null)
  const scrollTo = (k: string) => {
    const go = () => {
      const el = document.getElementById(`nb-${k}`)
      if (!el) return
      const h = heroRef.current?.offsetHeight || 64
      window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - h - 8 })
    }
    // 卡体懒加载后高度变化，稍后再对齐一次
    requestAnimationFrame(go)
    setTimeout(go, 350)
    setTimeout(go, 1000)
  }
  const routeLocked = !!routeKey && flow.find((x) => x.key === routeKey)?.status === 'locked'
  // 深链 / 路由变化：展开对应阶段并滚到卡顶
  useEffect(() => {
    if (routeKey) {
      const k = routeLocked ? firstOpen?.key || null : routeKey
      setOpen(k)
      if (k) scrollTo(k)
    }
  }, [routeKey, routeLocked]) // eslint-disable-line react-hooks/exhaustive-deps
  // 确认后：折叠当前、展开下一节
  const prev = useRef<Record<string, string>>({})
  useEffect(() => {
    if (open) {
      const st = flow.find((s) => s.key === open)!
      const was = prev.current[open]
      if (was && was !== 'confirmed' && st.status === 'confirmed') {
        const nx = flow[FLOW_ORDER.indexOf(open) + 1]
        // 阶段页自己可能已带参数跳转（如 ?auto=1），只在仍停留在本阶段时补跳
        const from = open
        setTimeout(() => {
          if (stageKeyFromPath(window.location.pathname) !== from) return
          if (nx && nx.status !== 'locked') navigate(`/p/${id}/${nx.key}`)
          else setOpen(null)
        }, 0)
      }
    }
    prev.current = Object.fromEntries(flow.map((s) => [s.key, s.status]))
  }, [flow]) // eslint-disable-line react-hooks/exhaustive-deps

  const done = flow.filter((s) => s.status === 'confirmed').length
  const runningStage = flow.find((s) => runOf(s.key))
  const sub = runningStage
    ? `正在：${STAGE_TITLES[runningStage.key]}（后台任务运行中）`
    : done === 6
      ? '全流程完成'
      : `${done}/6 已确认 · 当前：${STAGE_TITLES[(firstOpen || flow[0]).key]}`
  const toggle = (s: FlowStage) => {
    if (s.status === 'locked') return
    if (open === s.key) setOpen(null)
    else navigate(`/p/${id}/${s.key}`)
  }
  return (
    <div className="nb">
      <header className="nb-hero" ref={heroRef}>
        <Link to="/" className="nb-logo" title="返回项目列表">
          HW
        </Link>
        <div className="nb-hero__txt">
          <h1 title={title}>{title}</h1>
          <p className={runningStage ? 'is-running' : ''}>
            {runningStage && <Loader2 size={11} className="ptl-spin" aria-hidden="true" />}
            {sub}
          </p>
        </div>
        <button type="button" className="nb-small" onClick={() => setReader({ kind: 'files' })}>
          <Folder size={13} aria-hidden="true" /> 全部文件
        </button>
        <Link to="/settings" className="nb-small is-icon" title="设置" aria-label="设置">
          <Settings2 size={14} />
        </Link>
      </header>
      <ModelBanner />
      <ol className="nb-tl" aria-label="研究阶段">
        {flow.map((s, i) => (
          <Section
            key={s.key}
            s={s}
            idx={i}
            open={open === s.key}
            running={runOf(s.key)}
            seconds={s.key === 'direction' ? undefined : seconds[s.key]}
            onToggle={() => toggle(s)}
            onArt={(key) => setReader({ kind: 'doc', key })}
          />
        ))}
      </ol>
      {reader && (
        <Reader
          reader={reader}
          flow={flow}
          onOpen={(key) => setReader({ kind: 'doc', key })}
          onClose={() => setReader(null)}
        />
      )}
    </div>
  )
}

function Section({
  s,
  idx,
  open,
  running,
  seconds,
  onToggle,
  onArt,
}: {
  s: FlowStage
  idx: number
  open: boolean
  running: boolean
  seconds?: number
  onToggle: () => void
  onArt: (key: string) => void
}) {
  const ds = dotState(s, running)
  const locked = s.status === 'locked'
  const arts = FILES.filter((f) => f.stage === s.key)
  return (
    <li id={`nb-${s.key}`} className={`nb-sec is-${ds} ${open ? 'is-open' : ''}`}>
      <span className="nb-dot" aria-hidden="true">
        {ds === 'confirmed' ? <Check size={10} /> : ds === 'locked' ? <Lock size={8} /> : null}
      </span>
      <div className="nb-card">
        <button
          type="button"
          className="nb-sh"
          aria-expanded={open}
          aria-disabled={locked}
          title={locked ? '先完成上一步' : undefined}
          onClick={onToggle}
        >
          <span className="nb-sh__nm">
            {idx + 1}. {STAGE_TITLES[s.key]}
          </span>
          <span className="nb-sh__sum" title={s.summary || undefined}>
            {locked
              ? '先完成上一步'
              : s.status === 'stale'
                ? STATUS_TEXT.stale
                : running
                  ? '后台任务运行中…'
                  : s.summary || STATUS_TEXT[s.status]}
          </span>
          {seconds !== undefined && <span className="nb-sh__du">{fmtDur(seconds)}</span>}
          {!locked && <ChevronDown size={14} className="nb-sh__cv" aria-hidden="true" />}
        </button>
        {open && !locked && <Body s={s} />}
        {!open && !locked && s.status !== 'active' && arts.length > 0 && (
          <div className="nb-arts">
            {arts.map((f) => {
              const Icon = f.icon
              return (
                <button key={f.key} type="button" className="mini-art" onClick={() => onArt(f.key)}>
                  <Icon size={12} aria-hidden="true" />
                  {f.name.replace(/\.(md|csv)$/, '')}
                  {s.version > 1 ? ` v${s.version}` : ''}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </li>
  )
}

/** 当前展开卡：嵌入阶段页 + 卡底操作（主按钮在右） */
function Body({ s }: { s: FlowStage }) {
  const navigate = useNavigate()
  const { projectId: id, flow, uiRef, local, edit, cancel } = useFlow()
  const llm = useLlm()
  const [asking, setAsking] = useState(false)
  const key = s.key
  const ui = uiRef.current
  const Page = PAGES[key]
  const nx = flow[FLOW_ORDER.indexOf(key) + 1]
  const editing = !!local.editing[key]
  let p: (PrimarySpec & { tone?: 'warn' }) | null
  if (s.status === 'confirmed' && !(key === 'proposal' && ui?.primary)) {
    p = nx
      ? {
          label:
            nx.status === 'stale'
              ? `更新：${STAGE_TITLES[nx.key]}`
              : `前往：${STAGE_TITLES[nx.key]}`,
          onClick: () => navigate(`/p/${id}/${nx.key}`),
        }
      : null
  } else if (ui?.primary) {
    const sp = ui.primary
    if (sp.needsLlm && llm.data && !llm.data.configured)
      p = {
        label: '去设置模型',
        tone: 'warn',
        reason: `尚未配置模型，无法${sp.label}`,
        onClick: () => navigate('/settings'),
      }
    else if (sp.error && !sp.busy)
      p = { ...sp, label: '重试', tone: 'warn', reason: sp.error, disabled: false }
    else p = sp
  } else p = null
  if (p?.busy) p = { ...p, label: p.label || '系统处理中…', disabled: true }
  const n = downstreamCount(flow, key)
  return (
    <div className="nb-body">
      {(editing || s.status === 'confirmed') && (
        <div className="nb-ro">
          {editing ? (
            <>
              <span className="status-badge is-orange">修改中 · 草稿自动保存</span>
              <button type="button" className="product-button is-quiet" onClick={() => cancel(key)}>
                放弃修改
              </button>
            </>
          ) : (
            <>
              <span className="muted">已确认，内容只读。</span>
              <button
                type="button"
                className="product-button is-quiet"
                onClick={() => setAsking(true)}
              >
                <Pencil size={13} aria-hidden="true" /> 修改
              </button>
            </>
          )}
        </div>
      )}
      <div className="stage-body">
        <Suspense fallback={loading}>
          <Page />
        </Suspense>
      </div>
      <div className="acts">
        {s.status !== 'confirmed' && <StepChecklist items={ui?.checklist} />}
        {p?.reason && (
          <span className={`flow-reason ${p.tone === 'warn' ? 'is-warn' : ''}`} title={p.reason}>
            {p.reason}
          </span>
        )}
        {p && (
          <button
            type="button"
            data-primary=""
            className={`product-button is-primary flow-primary pri ${p.tone === 'warn' ? 'is-warn' : ''}`}
            disabled={p.disabled}
            onClick={() => p!.onClick?.()}
          >
            {p.busy && <Loader2 size={14} className="flow-spin" aria-hidden="true" />}
            {p.label}
            {!p.busy && <ArrowRight size={14} aria-hidden="true" />}
          </button>
        )}
      </div>
      {asking &&
        createPortal(
          <div className="overlay">
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="edit-title"
              className="dialog"
            >
              <h2 id="edit-title">修改「{STAGE_TITLES[key]}」？</h2>
              <p>
                {n > 0
                  ? `修改后，后面 ${n} 个阶段需要重新确认。没受影响的内容会保留，重做时预先填好。`
                  : '修改后需要重新确认本阶段。'}
              </p>
              <div className="actions">
                <button type="button" className="quiet" onClick={() => setAsking(false)}>
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => {
                    edit(key)
                    ui?.onStartEdit?.()
                    setAsking(false)
                  }}
                >
                  继续修改
                </button>
              </div>
            </section>
          </div>,
          document.body,
        )}
    </div>
  )
}

/** 全屏白底阅读层：产物文档 / 全部文件。层内整页滚动。 */
function Reader({
  reader,
  flow,
  onOpen,
  onClose,
}: {
  reader: { kind: 'files' } | { kind: 'doc'; key: string }
  flow: FlowStage[]
  onOpen: (key: string) => void
  onClose: () => void
}) {
  const [params, setParams] = useSearchParams()
  const bodyRef = useRef<HTMLDivElement>(null)
  const file = reader.kind === 'doc' ? fileOf(reader.key) : null
  const stage = file ? (file.stage as StageKey) : null
  const st = stage ? flow.find((x) => x.key === stage) : null
  // 数据阶段的三个文件由 ?tab= 区分
  useLayoutEffect(() => {
    if (file?.key.startsWith('data?tab=')) {
      const t = file.key.split('=')[1]
      if (params.get('tab') !== t) {
        const nx = new URLSearchParams(params)
        nx.set('tab', t)
        setParams(nx, { replace: true })
      }
    }
  }, [file?.key]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    document.documentElement.classList.add('nb-reading')
    return () => {
      window.removeEventListener('keydown', k)
      document.documentElement.classList.remove('nb-reading')
    }
  }, [onClose])
  const text = () => bodyRef.current?.innerText || ''
  const Page = stage ? PAGES[stage] : null
  return (
    <div
      className="nb-reader"
      role="dialog"
      aria-modal="true"
      aria-label={file?.name || '全部文件'}
    >
      <div className="nb-reader__bar">
        {file ? (
          <ActionStrip
            file={file}
            a={{
              version: Math.max(1, st?.version || 1),
              onCopy: () => navigator.clipboard?.writeText(text()),
              onExport: () => {
                const own = bodyRef.current?.querySelector<HTMLButtonElement>(
                  '.doc-preview__bar button:last-child',
                )
                if (stage === 'proposal' && own) own.click()
                else downloadText(file.name, text())
              },
              onClose,
            }}
          />
        ) : (
          <div className="wb-act">
            <span className="wb-act__fn">
              <Folder size={14} aria-hidden="true" /> 全部文件
            </span>
            <button type="button" className="product-button is-quiet" onClick={onClose}>
              返回时间线
            </button>
          </div>
        )}
      </div>
      <div className="nb-reader__doc" ref={bodyRef}>
        {reader.kind === 'files' ? (
          <FilesView flow={flow} tabs={[]} onOpen={onOpen} />
        ) : (
          Page && (
            <ReaderCtx.Provider value={true}>
              <div className="stage-body">
                <Suspense fallback={loading}>
                  <Page />
                </Suspense>
              </div>
            </ReaderCtx.Provider>
          )
        )}
      </div>
    </div>
  )
}

export type { ReactNode }
