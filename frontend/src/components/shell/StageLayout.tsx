import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Folder,
  Loader2,
  Lock,
  Pencil,
  Settings2,
} from 'lucide-react'
import { STAGE_TITLES, STAGE_TODO, stageKeyFromPath, useOverview } from '../../lib/stages'
import { displayProjectTitle } from '../../lib/displayTitle'
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
  stale: '需重新确认',
}
const SHORT: Record<StageKey, string> = {
  direction: '研究方向',
  literature: '文献',
  candidates: '候选假设',
  plan: '研究方案',
  data: '数据与检验',
  proposal: '研究提案',
}
const loading = <p className="loading-line">正在加载…</p>

/** 分步向导（方案 I）：sticky 顶栏 + 六步 stepper + 产物芯片 + 当前阶段一张主卡。只有整页滚动。 */
export default function StageLayout() {
  const { id } = useParams()
  const overview = useOverview(id)
  if (!overview.data) return <p className="loading-line">正在读取项目…</p>
  return (
    <FlowProvider projectId={id!} stages={overview.data.stages} title={overview.data.project.title}>
      <Wizard title={overview.data.project.title} />
    </FlowProvider>
  )
}

function Wizard({ title }: { title: string }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { projectId: id, flow, runsSettled } = useFlow()
  const routeKey = stageKeyFromPath(pathname) as StageKey | undefined
  const firstOpen = flow.find((s) => s.status !== 'confirmed' && s.status !== 'locked')
  const { seconds, running } = useStageJobs(id)
  const runOf = (k: StageKey) => (k === 'data' ? running.data : running[k]) || false

  // 当前阶段：深链优先；锁定阶段回退到第一个未确认；默认方向
  const cur: StageKey =
    (routeKey && flow.find((x) => x.key === routeKey)?.status !== 'locked' ? routeKey : null) ||
    firstOpen?.key ||
    'direction'

  // 无阶段段：落到当前应打开的阶段。锁定深链：回退到第一个未确认。
  // runs 未 settle 前不把提案深链踢回（dataRunOk 可能尚未算出）
  useEffect(() => {
    if (!routeKey) navigate(`/p/${id}/${cur}`, { replace: true })
    else if (flow.find((x) => x.key === routeKey)?.status === 'locked') {
      if (routeKey === 'proposal' && !runsSettled) return
      navigate(`/p/${id}/${cur}`, { replace: true })
    }
  }, [routeKey, cur, runsSettled]) // eslint-disable-line react-hooks/exhaustive-deps

  // 确认后：若仍停在刚确认的阶段，跳到下一节（阶段页自己的 navigate 优先；这里兜底）
  const prevStatus = useRef<Record<string, string>>({})
  useEffect(() => {
    const st = flow.find((x) => x.key === cur)
    const was = prevStatus.current[cur]
    if (st && was && was !== 'confirmed' && st.status === 'confirmed') {
      const nx = flow[FLOW_ORDER.indexOf(cur) + 1]
      if (nx && nx.status !== 'locked') {
        const from = cur
        setTimeout(() => {
          if (stageKeyFromPath(window.location.pathname) === from) navigate(`/p/${id}/${nx.key}`)
        }, 50)
      }
    }
    prevStatus.current = Object.fromEntries(flow.map((x) => [x.key, x.status]))
  }, [flow]) // eslint-disable-line react-hooks/exhaustive-deps

  const [reader, setReader] = useState<null | { kind: 'files' } | { kind: 'doc'; key: string }>(
    null,
  )
  const done = flow.filter((s) => s.status === 'confirmed').length
  const runningStage = flow.find((s) => runOf(s.key))
  const dataWarn = flow.some((s) => s.key === 'data' && s.backend === 'failed')
  const badge = runningStage
    ? '运行中'
    : done === 6
      ? '全流程完成'
      : flow.some((s) => s.status === 'stale')
        ? '需更新'
        : dataWarn
          ? '主模型已完成'
          : '进行中'
  const go = (k: StageKey) => {
    const s = flow.find((x) => x.key === k)
    if (!s || s.status === 'locked') return
    navigate(`/p/${id}/${k}`)
  }
  const prev = FLOW_ORDER[FLOW_ORDER.indexOf(cur) - 1] as StageKey | undefined

  return (
    <div className="wz">
      <header className="wz-top">
        <div className="wz-top__row">
          <Link to="/" className="nb-logo hw-mark" title="返回工作台首页">
            <img className="hw-mark__img" src="/brand/hw-logo.svg" alt="" draggable={false} />
          </Link>
          <Link to="/?view=projects" className="wz-top__crumb" title="查看全部研究项目">
            工作台
          </Link>
          <span className="wz-top__sep" aria-hidden="true">
            /
          </span>
          <h1 title={displayProjectTitle(title, id)}>{displayProjectTitle(title, id)}</h1>
          <span className={`wz-badge ${runningStage ? 'is-run' : done === 6 ? 'is-ok' : ''}`}>
            {runningStage && <Loader2 size={11} className="ptl-spin" aria-hidden="true" />}
            {badge}
          </span>
          <Link to="/" className="nb-small wz-top__home" title="回到首页或新建研究">
            工作台首页
          </Link>
          <Link to="/settings" className="nb-small is-icon" title="设置" aria-label="设置">
            <Settings2 size={14} />
          </Link>
        </div>
        <nav className="wz-stepper" aria-label="研究阶段">
          {flow.map((s, i) => {
            const ds = dotState(s, runOf(s.key))
            const on = s.key === cur
            const sec = s.key === 'direction' ? undefined : seconds[s.key]
            return (
              <span key={s.key} className="wz-step-wrap">
                {i > 0 && <span className="wz-ss" aria-hidden="true" />}
                <button
                  type="button"
                  className={`wz-sp is-${ds} ${on ? 'is-on' : ''}`}
                  disabled={s.status === 'locked'}
                  title={
                    s.status === 'locked'
                      ? '先完成上一步'
                      : `${STAGE_TITLES[s.key]} · ${STATUS_TEXT[ds]}${sec !== undefined ? ` · ${fmtDur(sec)}` : ''}`
                  }
                  aria-current={on ? 'step' : undefined}
                  onClick={() => go(s.key)}
                >
                  <span className="wz-sp__n" aria-hidden="true">
                    {ds === 'running' ? (
                      <Loader2 size={10} className="ptl-spin" />
                    ) : ds === 'confirmed' ? (
                      <Check size={10} />
                    ) : ds === 'locked' ? (
                      <Lock size={8} />
                    ) : (
                      i + 1
                    )}
                  </span>
                  <span className="wz-sp__lab">{SHORT[s.key]}</span>
                  {ds === 'confirmed' && sec !== undefined && (
                    <span className="wz-sp__du">{fmtDur(sec)}</span>
                  )}
                </button>
              </span>
            )
          })}
        </nav>
      </header>
      <ModelBanner />
      <main className="wz-main" id="main-content">
        <div className="wz-chips" aria-label="已完成产物">
          {FILES.filter((f) => {
            const st = flow.find((x) => x.key === f.stage)
            return st && st.status !== 'locked' && st.status !== 'active' && f.stage !== cur
          }).map((f) => {
            const Icon = f.icon
            return (
              <button
                key={f.key}
                type="button"
                className="wz-chip"
                onClick={() => setReader({ kind: 'doc', key: f.key })}
              >
                <Icon size={12} aria-hidden="true" />
                {f.name.replace(/\.(md|csv)$/, '')}
              </button>
            )
          })}
          <button
            type="button"
            className="wz-chip is-ghost"
            onClick={() => setReader({ kind: 'files' })}
          >
            <Folder size={12} aria-hidden="true" /> 全部文件
          </button>
        </div>
        <StageCard
          s={flow.find((x) => x.key === cur)!}
          running={runOf(cur)}
          onPrev={prev ? () => go(prev) : undefined}
        />
      </main>
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

function StageCard({
  s,
  running,
  onPrev,
}: {
  s: FlowStage
  running: boolean
  onPrev?: () => void
}) {
  const navigate = useNavigate()
  const { projectId: id, flow, uiRef, local, edit, cancel } = useFlow()
  const llm = useLlm()
  const [asking, setAsking] = useState(false)
  const key = s.key
  const ui = uiRef.current
  const Page = PAGES[key]
  const nx = flow[FLOW_ORDER.indexOf(key) + 1]
  const editing = !!local.editing[key]
  const ds = dotState(s, running)

  let p: (PrimarySpec & { tone?: 'warn' }) | null
  if (s.status === 'confirmed' && !(key === 'proposal' && ui?.primary)) {
    p = nx
      ? {
          label:
            nx.status === 'stale'
              ? `更新：${STAGE_TITLES[nx.key]}`
              : `下一步：${STAGE_TITLES[nx.key]}`,
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
    <section className={`wz-card is-${ds}`} aria-labelledby="wz-card-title">
      <header className="wz-card__hd">
        <div className="wz-card__hd-main">
          <h2 id="wz-card-title">
            {FLOW_ORDER.indexOf(key) + 1}. {STAGE_TITLES[key]}
          </h2>
          <p className="wz-card__sub">
            {s.status === 'confirmed' && !editing
              ? '已确认，内容只读。可点右侧「修改」重新编辑。'
              : STAGE_TODO[key] || ''}
          </p>
        </div>
        <div className="wz-card__hd-acts">
          {editing ? (
            <>
              <span className="status-badge is-orange">修改中 · 草稿自动保存</span>
              <button
                type="button"
                className="product-button is-quiet nb-hd-btn"
                onClick={() => cancel(key)}
              >
                放弃修改
              </button>
            </>
          ) : (
            <>
              <span className={`wz-badge is-${ds}`}>{STATUS_TEXT[ds]}</span>
              {s.status === 'confirmed' && (
                <button
                  type="button"
                  className="product-button is-quiet nb-hd-btn"
                  onClick={() => setAsking(true)}
                >
                  <Pencil size={12} aria-hidden="true" /> 修改
                </button>
              )}
            </>
          )}
        </div>
      </header>
      <div className="stage-body">
        <Suspense fallback={loading}>
          <Page />
        </Suspense>
      </div>
      <footer className="acts">
        {onPrev ? (
          <button type="button" className="product-button is-quiet" onClick={onPrev}>
            <ArrowLeft size={14} aria-hidden="true" /> 上一步
          </button>
        ) : (
          <span />
        )}
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
      </footer>
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
    </section>
  )
}

/** 全屏白底阅读层：产物文档 / 全部文件 */
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
              返回向导
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
