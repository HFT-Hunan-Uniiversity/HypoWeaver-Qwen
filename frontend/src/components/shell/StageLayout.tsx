import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, CircleHelp, Loader2, Pencil } from 'lucide-react'
import { ModelBanner, ScrollFab } from './AppShell'
import {
  ActionStrip,
  ChatPane,
  DocToc,
  FilesView,
  PlanDots,
  TabBar,
  downloadText,
  fileOf,
  hrefOf,
  keyOf,
  useOpenStage,
  useStageSeconds,
  useTabs,
} from './Workbench'
import {
  STAGE_INTRO,
  STAGE_TITLES,
  STAGE_TODO,
  stageKeyFromPath,
  useOverview,
} from '../../lib/stages'
import { useLlm } from '../../lib/llm'
import { downstreamCount, nextFlowStage, type StageKey } from '../../lib/flow'
import { FlowProvider, useFlow, type PrimarySpec } from '../flow/FlowContext'
import { IntroCard, StepChecklist, useIntro } from '../flow/FlowBits'

/** 阶段页外壳：一行页头（阶段条 + 唯一主按钮）+ 一行"这里做什么 / 任务清单" + 全宽工作区 */
export default function StageLayout() {
  const { id } = useParams()
  const overview = useOverview(id)
  if (!overview.data) return <p className="loading-line">正在读取项目…</p>
  return (
    <FlowProvider projectId={id!} stages={overview.data.stages}>
      <Shell />
    </FlowProvider>
  )
}

function Shell() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const { projectId: id, flow, uiRef, local, edit, cancel } = useFlow()
  const llm = useLlm()
  const key = stageKeyFromPath(pathname) as StageKey | undefined
  const isOverview = !key
  const st = key ? flow.find((s) => s.key === key)! : undefined
  const next = nextFlowStage(flow)
  const ui = uiRef.current
  const intro = useIntro(key || 'overview')
  const [asking, setAsking] = useState(false)
  const go = (k: string) => navigate(`/p/${id}/${k}`)

  // —— 主按钮：由流程状态和页面声明共同决定 ——
  let p: PrimarySpec & { tone?: 'warn' }
  if (isOverview || !st) {
    p = next
      ? {
          label:
            next.status === 'stale'
              ? `更新：${STAGE_TITLES[next.key]}`
              : `继续：${STAGE_TITLES[next.key]}`,
          onClick: () => go(next.key),
        }
      : { label: '查看研究提案', onClick: () => go('proposal') }
  } else if (st.status === 'locked') {
    p = {
      label: next ? `回到：${STAGE_TITLES[next.key]}` : '回到总览',
      onClick: () => (next ? go(next.key) : navigate(`/p/${id}`)),
    }
  } else if (st.status === 'confirmed' && !(key === 'proposal' && ui?.primary)) {
    if (next?.status === 'stale')
      p = {
        label: '更新下一阶段',
        tone: 'warn',
        onClick: () => go(next.key),
        reason: `「${STAGE_TITLES[next.key]}」需要更新`,
      }
    else if (next) p = { label: `前往：${STAGE_TITLES[next.key]}`, onClick: () => go(next.key) }
    else p = { label: '查看研究提案', onClick: () => go('proposal') }
  } else if (ui?.primary) {
    const s = ui.primary
    if (s.needsLlm && llm.data && !llm.data.configured)
      p = {
        label: '去设置模型',
        tone: 'warn',
        reason: `尚未配置模型，无法${s.label}`,
        onClick: () => navigate('/settings'),
      }
    else if (s.error && !s.busy)
      p = { ...s, label: '重试', tone: 'warn', reason: s.error, disabled: false }
    else p = s
  } else p = { label: '…', disabled: true }
  if (p.busy) p = { ...p, label: p.label || '系统处理中…', disabled: true }

  const editable = st && st.status === 'confirmed'
  const editing = key && local.editing[key]
  const n = key ? downstreamCount(flow, key) : 0
  // —— 工作台：标签页 / 全部文件 / 对话栏 ——
  const overview = useOverview(id)
  const fileKey = keyOf(key, search)
  const file = fileOf(fileKey)
  const [tabs, setTabs] = useTabs(id, fileKey)
  const [files, setFiles] = useState(false)
  const [fs, setFs] = useState(false)
  useEffect(() => setFiles(false), [pathname, search])
  const seconds = useStageSeconds(id)
  const openStage = useOpenStage(id)
  const openKey = (k: string) => {
    setFiles(false)
    if (!tabs.includes(k)) setTabs([...tabs, k])
    navigate(hrefOf(id, k))
  }
  const closeKey = (k: string) => {
    const i = tabs.indexOf(k)
    const rest = tabs.filter((x) => x !== k)
    setTabs(rest)
    if (k === fileKey) {
      if (rest.length) navigate(hrefOf(id, rest[Math.max(0, i - 1)]))
      else setFiles(true)
    }
  }
  const docText = () =>
    (document.querySelector('.stage-body') as HTMLElement | null)?.innerText || ''
  const regenOk =
    ui?.primary &&
    /生成/.test(ui.primary.label) &&
    !ui.primary.disabled &&
    !ui.primary.busy &&
    !(ui.primary.needsLlm && llm.data && !llm.data.configured)
  const strip = (
    <ActionStrip
      file={file}
      a={{
        version: Math.max(1, st?.version || 1),
        onCopy: () => navigator.clipboard?.writeText(docText()),
        onExport: () => {
          const own = document.querySelector<HTMLButtonElement>(
            '.doc-preview__bar button:last-child',
          )
          if (key === 'proposal' && own) own.click()
          else downloadText(file.name, docText())
        },
        edit: editable
          ? {
              onClick: () => {
                setFiles(false)
                setAsking(true)
              },
              title: '修改此阶段（会使后续阶段需要更新）',
            }
          : {
              title: editing
                ? '正在修改中'
                : st?.status === 'locked'
                  ? '未解锁'
                  : '本阶段尚未确认，可直接在文档中编辑',
            },
        regen: regenOk
          ? { onClick: () => ui!.primary!.onClick?.(), title: ui!.primary!.label }
          : { title: '当前没有可用的重新生成操作' },
        fs,
        onFs: () => setFs(!fs),
      }}
    />
  )
  return (
    <div className={`wb ${fs ? 'is-fs' : ''}`}>
      <ChatPane
        title={overview.data?.project.title || ''}
        direction={overview.data?.project.direction?.text || ''}
        flow={flow}
        banner={<ModelBanner />}
        plan={<PlanDots flow={flow} currentStage={key} seconds={seconds} onOpen={openStage} />}
        strip={strip}
      />
      <section className="wb-right">
        <TabBar
          tabs={tabs}
          active={files ? null : fileKey}
          files={files}
          onOpen={openKey}
          onClose={closeKey}
          onFiles={() => setFiles(!files)}
          onExitFs={fs ? () => setFs(false) : undefined}
        />
        <main id="main-content" className="shell-view">
          {files ? (
            <FilesView flow={flow} tabs={tabs} onOpen={openKey} />
          ) : (
            <div className="stage-page">
              <header className="page-bar no-print">
                <div className="doc-crumb" title={file.name}>
                  {key ? STAGE_TITLES[key] : '总览'} <span>/</span> <strong>{file.name}</strong>
                </div>
                <div className="page-bar__actions">
                  {p.reason && (
                    <span
                      className={`flow-reason ${p.tone === 'warn' ? 'is-warn' : ''}`}
                      title={p.reason}
                    >
                      {p.reason}
                    </span>
                  )}
                  <button
                    type="button"
                    data-primary=""
                    className={`product-button is-primary flow-primary ${p.tone === 'warn' ? 'is-warn' : ''}`}
                    disabled={p.disabled}
                    onClick={() => p.onClick?.()}
                  >
                    {p.busy && <Loader2 size={14} className="flow-spin" aria-hidden="true" />}
                    {p.label}
                    {!p.busy && <ArrowRight size={14} aria-hidden="true" />}
                  </button>
                </div>
              </header>
              {key && st && st.status !== 'locked' && (
                <div className="flow-subhead no-print">
                  <h1>{STAGE_TITLES[key]}</h1>
                  {st.version > 1 && <span className="flow-ver">v{st.version}</span>}
                  {st.status === 'stale' && (
                    <span className="status-badge is-yellow">需要更新</span>
                  )}
                  {st.status === 'confirmed' && (
                    <span className="status-badge is-green">已确认</span>
                  )}
                  {editing && <span className="status-badge is-orange">修改中 · 草稿自动保存</span>}
                  <p className="flow-todo">
                    {st.status === 'confirmed' ? '已确认，内容只读。' : STAGE_TODO[key]}
                  </p>
                  {st.status !== 'confirmed' && <StepChecklist items={ui?.checklist} />}
                  {editable && (
                    <button
                      type="button"
                      className="product-button is-quiet"
                      onClick={() => setAsking(true)}
                    >
                      <Pencil size={13} aria-hidden="true" /> 修改此阶段
                    </button>
                  )}
                  {editing && (
                    <button
                      type="button"
                      className="product-button is-quiet"
                      onClick={() => cancel(key)}
                    >
                      放弃修改
                    </button>
                  )}
                  <button
                    type="button"
                    className="icon-button"
                    title="这一阶段做什么"
                    aria-label="这一阶段做什么"
                    onClick={intro.show}
                  >
                    <CircleHelp size={15} />
                  </button>
                </div>
              )}
              {key && intro.open && st?.status !== 'locked' && (
                <IntroCard text={STAGE_INTRO[key]} onClose={intro.dismiss} />
              )}
              <div className={`wb-docgrid ${key === 'plan' || key === 'proposal' ? 'no-toc' : ''}`}>
                {key !== 'plan' && key !== 'proposal' && <DocToc deps={pathname + search} />}
                <div className="stage-body">
                  {st?.status === 'locked' ? (
                    <section className="flow-empty fill">
                      <h2>「{STAGE_TITLES[key!]}」还没解锁</h2>
                      <p>
                        流程按顺序进行。先完成
                        {next ? `「${STAGE_TITLES[next.key]}」` : '前面的阶段'}
                        ，这里会自动解锁。
                      </p>
                    </section>
                  ) : (
                    <Outlet />
                  )}
                </div>
              </div>
              {asking && key && (
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
                        ? `修改后，后面 ${n} 个阶段需要更新。没受影响的内容会保留，重做时预先填好。`
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
                </div>
              )}
            </div>
          )}
        </main>
        <ScrollFab />
      </section>
    </div>
  )
}
