import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FileStack, Trash2 } from 'lucide-react'
import { AppSidebar, sidebarTasks, type ShellNav } from './components/AppSidebar'
import { DiscoveryPage } from './components/DiscoveryPage'
import { MainToolbar } from './components/MainToolbar'
import { LiteratureReaderPage } from './components/LiteratureReaderPage'
import { PreflightPanel } from './components/PreflightPanel'
import { ProjectOverviewPage } from './components/ProjectOverviewPage'
import { ProjectsPage } from './components/ProjectsPage'
import { ResearchInputForm } from './components/ResearchInputForm'
import { ResourceLibraryPage } from './components/ResourceLibraryPage'
import { SystemConfigPanel } from './components/SystemConfigPanel'
import { TaskComposer } from './components/TaskComposer'
import { TaskResearchRail } from './components/TaskResearchRail'
import { MockTaskStream, RunTaskStream } from './components/TaskStream'
import { WorkspaceDrawer } from './components/WorkspaceDrawer'
import { demoResearchDraft, emptyResearchDraft, preflightResearch, type ResearchDraft } from './data/researchDraft'
import {
  type MockGateAction,
  type MockMode,
  type MockTask,
  type MockTaskSummary,
} from './data/mockPipeline'
import {
  frontendDataSource,
  SHOWCASE_PROJECT_ID,
  SHOWCASE_TASK_ID,
  type DiscoveryHandoff,
  type Project,
} from './product'
import { normalizeCaseSubmission, workflowApi } from './runtime/api'
import { selectCaseFolder, type CaseFolderSelection } from './runtime/caseFolder'
import { hashOf, isProjectView, viewFromHash, type DiscoveryStep, type ShellView } from './runtime/router'
import { getTheme, toggleTheme, type ThemeMode } from './runtime/theme'
import type { BaselineRun, CaseImportReport, CaseSubmissionInput, ConnectionTestResult, GateDecisionInput, Group1VerifiedBundleStatus, RunSnapshot, RunSummary, RuntimeConfigStatus, RuntimeConfigUpdate, WorkflowDefinition } from './runtime/types'

const isPublicDemo = import.meta.env.VITE_PUBLIC_DEMO === 'true'
const SIDEBAR_KEY = 'hw-sidebar'
const {
  createProject,
  deleteProjects: removeProjects,
  getProject,
  getSelectedProjectId,
  listProjects,
  listDemoTasks: listMockTasks,
  setSelectedProjectId,
  subscribeDemoTask: subscribeMockTask,
  subscribeDemoTasks: subscribeMockTasks,
  subscribe: subscribeProductStore,
  updateProject,
  createDemoTask: createMockTask,
  decideDemoGate: decideMockGate,
  deleteDemoTask: deleteMockTask,
  getDemoTask: getMockTask,
  isDemoTaskId: isMockTaskId,
} = frontendDataSource
const DISCOVERY_STEP_LABELS: Record<DiscoveryStep, string> = {
  brief: '研究简报',
  resources: '数据中心检索',
  gaps: '趋势与空白',
  ideas: '候选假设',
  decision: '假设选择',
  handoff: '方案输入',
}
const LIBRARY_LABELS = {
  literature: '文献库',
  policy: '政策库',
  dataset: '数据库',
  method: '方法库',
} as const

function displayResearchTitle(value: string): string {
  const normalized = value
    .replace(/[？?。.]$/u, '')
    .replace('如何影响', '与')
    .replace(/改革创新试验区/u, '')
    .replace(/政策政策/u, '政策')
    .trim()
  return normalized.length > 28 ? `${normalized.slice(0, 28)}…` : normalized
}

export function App() {
  const [view, setView] = useState<ShellView>(() => viewFromHash())
  const [definition, setDefinition] = useState<WorkflowDefinition | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [run, setRun] = useState<RunSnapshot | null>(null)
  const [mockTasks, setMockTasks] = useState<MockTaskSummary[]>(() => listMockTasks())
  const [mockTask, setMockTask] = useState<MockTask | null>(null)
  const [projects, setProjects] = useState<Project[]>(() => listProjects())
  const [theme, setTheme] = useState<ThemeMode>(() => getTheme())
  const [config, setConfig] = useState<RuntimeConfigStatus | null>(null)
  const [group1Bundle, setGroup1Bundle] = useState<Group1VerifiedBundleStatus | null>(null)
  const [accessTokenPresent, setAccessTokenPresent] = useState(() => workflowApi.hasAccessToken())
  const [accessTokenVerified, setAccessTokenVerified] = useState(false)
  const [draft, setDraft] = useState<ResearchDraft>(() => emptyResearchDraft())
  const [importReport, setImportReport] = useState<CaseImportReport | null>(null)
  const [showPreflight, setShowPreflight] = useState(false)
  const [showAdvancedInput, setShowAdvancedInput] = useState(false)
  const [baselineRun, setBaselineRun] = useState<BaselineRun | null>(null)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === 'collapsed')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [busyLabel, setBusyLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const runRequestRef = useRef(0)
  const runIdRef = useRef<string | null>(null)

  const refreshRuns = useCallback(async () => {
    const nextRuns = await workflowApi.listRuns()
    setRuns(nextRuns)
    return nextRuns
  }, [])

  const refreshConfig = useCallback(async () => {
    const nextConfig = await workflowApi.getRuntimeConfig()
    setConfig(nextConfig)
  }, [])

  /* —— 后端初始化：失败不阻塞壳层（mock 全流程仍可用）—— */
  useEffect(() => {
    if (isPublicDemo) {
      setLoading(false)
      return
    }
    let cancelled = false
    Promise.all([
      workflowApi.getDefinition(),
      workflowApi.getRuntimeConfig(),
      workflowApi.listRuns(),
      workflowApi.getVerifiedGroup1Bundle(),
    ])
      .then(([nextDefinition, nextConfig, nextRuns, nextGroup1Bundle]) => {
        if (cancelled) return
        setDefinition(nextDefinition)
        setConfig(nextConfig)
        setRuns(nextRuns)
        setGroup1Bundle(nextGroup1Bundle)
      })
      .catch((reason) => {
        if (!cancelled) setError(`无法连接工作流后端（${reason instanceof Error ? reason.message : String(reason)}）。演示任务不受影响；真实研究请先启动后端。`)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  /* —— Hash Router：旧 #studio / #runs 只做一次兼容重定向 —— */
  useEffect(() => {
    const syncHash = () => {
      const legacyHash = window.location.hash.replace('#', '')
      if (legacyHash === 'runs' || legacyHash === 'studio') {
        window.history.replaceState(null, '', legacyHash === 'studio' ? '#projects' : '#new')
      }
      setView(viewFromHash())
    }
    window.addEventListener('hashchange', syncHash)
    return () => window.removeEventListener('hashchange', syncHash)
  }, [])

  /* —— mock 任务列表订阅（侧边栏）—— */
  useEffect(() => subscribeMockTasks(() => setMockTasks(listMockTasks())), [])

  /* —— 前端项目与资源篮订阅（localStorage fixture store）—— */
  useEffect(() => subscribeProductStore(() => setProjects(listProjects())), [])

  /* —— 任务视图：mock 订阅 / 真实运行加载 —— */
  const taskId = view.kind === 'task' ? view.id : null
  useEffect(() => {
    setWorkspaceOpen(false)
    if (!taskId) {
      setMockTask(null)
      return
    }
    if (isMockTaskId(taskId)) {
      setMockTask(getMockTask(taskId))
      setRun(null)
      setBaselineRun(null)
      runIdRef.current = null
      return subscribeMockTask(taskId, (next) => setMockTask({ ...next, stages: next.stages.map((stage) => ({ ...stage })) }))
    }
    setMockTask(null)
    if (runIdRef.current === taskId && run) return
    let cancelled = false
    const requestId = ++runRequestRef.current
    setBusy(true)
    setBusyLabel('正在恢复持久化运行状态…')
    setError(null)
    workflowApi.getRun(taskId)
      .then(async (nextRun) => {
        const nextBaselines = await workflowApi.listAgentLaboratoryRuns(nextRun.caseId).catch(() => [])
        if (cancelled || requestId !== runRequestRef.current) return
        runIdRef.current = nextRun.id
        setRun(nextRun)
        setBaselineRun(nextBaselines[0] ?? null)
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => {
        if (!cancelled && requestId === runRequestRef.current) {
          setBusy(false)
          setBusyLabel('')
        }
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId])

  /* —— 基线轮询 —— */
  useEffect(() => {
    if (!baselineRun || !['queued', 'running'].includes(baselineRun.status)) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      workflowApi.getAgentLaboratoryRun(baselineRun.id)
        .then((nextRun) => { if (!cancelled) setBaselineRun(nextRun) })
        .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) })
    }, 1500)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [baselineRun])

  const preflightItems = useMemo(
    () => preflightResearch(draft, config, accessTokenVerified),
    [accessTokenVerified, config, draft],
  )

  const sidebarItems = useMemo(() => sidebarTasks(mockTasks, runs), [mockTasks, runs])

  async function withBusy<T>(label: string, operation: () => Promise<T>): Promise<T | null> {
    setBusy(true)
    setBusyLabel(label)
    setError(null)
    try {
      return await operation()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      return null
    } finally {
      setBusy(false)
      setBusyLabel('')
    }
  }

  function changeView(nextView: ShellView) {
    if (isProjectView(nextView)) setSelectedProjectId(nextView.id)
    setView(nextView)
    window.history.replaceState(null, '', hashOf(nextView))
    setDrawerOpen(false)
    if (nextView.kind === 'new') setShowAdvancedInput(false)
    if (nextView.kind !== 'new') setShowPreflight(false)
  }

  function navigate(nav: ShellNav) {
    if (nav === 'library') {
      changeView({ kind: 'library', resourceKind: 'literature' })
      return
    }
    changeView({ kind: nav })
  }

  function openProject(id: string) {
    changeView({ kind: 'project', id, section: 'overview' })
  }

  function openDiscovery(id: string, step: DiscoveryStep = 'brief') {
    changeView({ kind: 'discovery', id, step })
  }

  function openLibrary(resourceKind: 'literature' | 'policy' | 'dataset' | 'method' = 'literature') {
    changeView({ kind: 'library', resourceKind })
  }

  function openLiteratureReader(resourceId: string) {
    changeView({ kind: 'reader', id: resourceId })
  }

  function openTask(id: string) {
    changeView({ kind: 'task', id })
  }

  function toggleCollapse() {
    setCollapsed((current) => {
      const next = !current
      localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'expanded')
      return next
    })
  }

  function toggleMobileSidebar() {
    setDrawerOpen((current) => {
      if (!current && collapsed) {
        setCollapsed(false)
        localStorage.setItem(SIDEBAR_KEY, 'expanded')
      }
      return !current
    })
  }

  function handleCreateProject(prompt: string, mode: MockMode) {
    const normalized = prompt.replace(/\s+/g, ' ').trim()
    const title = normalized.length > 30 ? `${normalized.slice(0, 30)}…` : normalized
    try {
      const normalizedShowcasePrompt = normalized.replace(/[？?]/g, '')
      const showcaseProject = getProject(SHOWCASE_PROJECT_ID)
      if (
        normalizedShowcasePrompt === '碳市场如何影响企业绿色创新'
        && showcaseProject
      ) {
        frontendDataSource.updateDiscoveryDraft(SHOWCASE_PROJECT_ID, {
          currentStep: 1,
          completedSteps: [],
          selectedIdeaId: undefined,
          scientificTen: showcaseProject.discovery.scientificTen,
        })
        updateProject(SHOWCASE_PROJECT_ID, { status: 'active' })
        setSelectedProjectId(SHOWCASE_PROJECT_ID)
        setProjects(listProjects())
        openDiscovery(SHOWCASE_PROJECT_ID)
        return
      }
      const project = createProject({
        title,
        summary: normalized,
        mode,
        brief: { researchQuestion: normalized },
      })
      setProjects(listProjects())
      openDiscovery(project.id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function handleCreateDemoTask(projectId: string, handoff: DiscoveryHandoff) {
    const project = getProject(projectId)
    if (!project) return
    if (projectId === SHOWCASE_PROJECT_ID && getMockTask(SHOWCASE_TASK_ID)) {
      updateProject(projectId, {
        status: 'handoff_ready',
        taskIds: Array.from(new Set([...project.taskIds, SHOWCASE_TASK_ID])),
      })
      setMockTasks(listMockTasks())
      setProjects(listProjects())
      openTask(SHOWCASE_TASK_ID)
      return
    }
    let task: MockTask
    try {
      task = createMockTask(handoff.caseInput.title || project.title, project.mode)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      return
    }
    updateProject(projectId, {
      status: 'handoff_ready',
      taskIds: Array.from(new Set([...project.taskIds, task.id])),
    })
    setMockTasks(listMockTasks())
    setProjects(listProjects())
    openTask(task.id)
  }

  function handleMockGate(gate: string, action: MockGateAction, comment?: string) {
    if (!taskId) return
    const next = decideMockGate(taskId, gate as MockTask['currentGate'] & string, action, comment)
    if (next) setMockTask({ ...next, stages: next.stages.map((stage) => ({ ...stage })) })
  }

  function handleDeleteMockTask() {
    if (!taskId || !mockTask) return
    const confirmed = window.confirm(`确定删除“${mockTask.title}”这条演示任务吗？`)
    if (!confirmed) return
    for (const project of listProjects()) {
      if (!project.taskIds.includes(taskId)) continue
      updateProject(project.id, {
        taskIds: project.taskIds.filter((id) => id !== taskId),
      })
    }
    deleteMockTask(taskId)
    setProjects(listProjects())
    changeView({ kind: 'new' })
  }

  async function startResearch() {
    if (isPublicDemo) {
      setError('公开演示版不连接研究后端，不能创建或保存真实任务。请在本地版中执行。')
      return
    }
    const nextRun = await withBusy('正在接收研究任务并执行输入校验…', () => workflowApi.createRun({ mode: draft.mode, case: draft.case }))
    if (!nextRun) return
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns()
    setShowPreflight(false)
    setShowAdvancedInput(false)
    openTask(nextRun.id)
  }

  async function startBaseline(caseInput: CaseSubmissionInput = draft.case) {
    if (isPublicDemo) {
      setError('公开演示版不连接 Agent Laboratory，不能启动真实基线任务。')
      return
    }
    if (!caseInput.datasetRefs.length) {
      setError('当前页面没有可复用的数据文件，请重新选择 CSV。')
      return
    }
    if (!config?.qwenApiKey.configured) {
      setError('请先在“设置”中保存并测试千问 API。')
      return
    }
    const approved = window.confirm('Agent Laboratory 会在本机执行其生成的 Python 代码。仅应使用可信数据；是否启动本次基线运行？')
    if (!approved) return
    const nextRun = await withBusy('正在启动 Agent Laboratory…', () => workflowApi.startAgentLaboratory(caseInput))
    if (!nextRun) return
    setBaselineRun(nextRun)
  }

  async function importCaseFile(file: File, target: 'hypoweaver' | 'agent-laboratory' = 'hypoweaver', folder?: CaseFolderSelection) {
    const imported = await withBusy(`正在上传并分析 ${file.name}…`, () => workflowApi.uploadCaseFile(file))
    if (!imported) return
    if (folder) {
      const supplementaryRefs = folder.supplementaryData.length
        ? await withBusy('正在登记空间权重矩阵…', () => Promise.all(folder.supplementaryData.map((asset) => workflowApi.uploadCaseAsset(asset))))
        : []
      if (supplementaryRefs === null) return
      const datasetRefs = [...imported.case.datasetRefs, ...supplementaryRefs]
      imported.report.hiddenFileCount = folder.hiddenFileCount
      imported.report.excludedFileCount = folder.excludedFileCount
      if (folder.caseProfile) {
        let profilePayload: unknown
        try {
          profilePayload = JSON.parse(await folder.caseProfile.text())
        } catch {
          setError('case_profile.json 不是有效的 JSON，已停止启动以避免使用错误研究定义。')
          return
        }
        const profile = normalizeCaseSubmission(profilePayload)
        imported.case = { ...profile, datasetRefs }
        imported.report.reviewItems.unshift('已读取 case_profile.json；数据引用由本次上传结果重新绑定。')
      } else {
        imported.case = { ...imported.case, datasetRefs }
      }
    }
    const importedDraft: ResearchDraft = { mode: 'research', case: imported.case }
    setDraft(importedDraft)
    setImportReport(imported.report)
    if (target === 'agent-laboratory') {
      await startBaseline(imported.case)
      return
    }
    const blockers = preflightResearch(importedDraft, config, accessTokenVerified)
      .filter((item) => item.level === 'blocker')
    if (blockers.length) {
      setShowPreflight(true)
      return
    }

    const nextRun = await withBusy('案例已安全导入，正在启动工作流并进入 H1…', () => workflowApi.createRun({ mode: importedDraft.mode, case: importedDraft.case }))
    if (!nextRun) return
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns()
    setShowPreflight(false)
    openTask(nextRun.id)
  }

  async function importGroup1Handoff(path: string, mode: 'research' | 'fixture') {
    if (isPublicDemo) {
      setError('公开演示版不能读取本机 Group 1 交接包；请在本地版执行。')
      return
    }
    const nextRun = await withBusy('正在校验 Group 1 冻结清单、生成 Group 2 可行性包并创建 H1 任务…', () => workflowApi.startGroup1Handoff(path, mode))
    if (!nextRun) return
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns()
    openTask(nextRun.id)
  }

  async function startVerifiedGroup1Bundle() {
    if (isPublicDemo) {
      setError('公开演示版不能启动本机已验证 Group 1 执行包；请在本地版执行。')
      return
    }
    if (group1Bundle?.status !== 'ready') {
      setError(group1Bundle?.message || '本机尚未发现可启动的 Group 1 已验证执行包。')
      return
    }
    const nextRun = await withBusy(
      '正在重新核验 Group 1 哈希、绑定真实执行面板并创建新的 H1 run…',
      () => workflowApi.startVerifiedGroup1Bundle(),
    )
    if (!nextRun) return
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns()
    openTask(nextRun.id)
  }

  async function openLaunchedDiscoveryRun(nextRun: RunSnapshot) {
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns().catch((reason) => {
      setError(reason instanceof Error ? reason.message : String(reason))
    })
    openTask(nextRun.id)
  }

  async function importCaseFolder(files: File[], target: 'hypoweaver' | 'agent-laboratory') {
    if (isPublicDemo) {
      setError('公开演示版仅用于浏览界面与交互，文件不会上传或保存。请使用本地版处理真实案例。')
      return
    }
    try {
      const selection = selectCaseFolder(files)
      await importCaseFile(selection.mainData, target, selection)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function deleteRun() {
    if (!run) return
    const confirmed = window.confirm(`确定删除“${run.caseName}”这条运行记录吗？此操作不会删除案例数据文件。`)
    if (!confirmed) return
    const nextRuns = await withBusy('正在删除运行记录…', async () => {
      await workflowApi.deleteRun(run.id)
      return workflowApi.listRuns()
    })
    if (!nextRuns) return
    setRuns(nextRuns)
    runIdRef.current = null
    setRun(null)
    setBaselineRun(null)
    changeView({ kind: 'new' })
  }

  async function deleteTasks(taskIds: string[]): Promise<boolean> {
    const availableIds = new Set(sidebarItems.map((item) => item.id))
    const uniqueIds = [...new Set(taskIds)].filter((id) => availableIds.has(id))
    if (!uniqueIds.length) return false

    const confirmed = window.confirm(
      `确定删除已选择的 ${uniqueIds.length} 条任务吗？此操作不会删除案例数据文件。`,
    )
    if (!confirmed) return false

    const result = await withBusy(`正在删除 ${uniqueIds.length} 条任务…`, async () => {
      const mockIds = uniqueIds.filter((id) => isMockTaskId(id))
      const runIds = uniqueIds.filter((id) => !isMockTaskId(id))
      const deletedIds = new Set<string>()
      const failures: string[] = []

      mockIds.forEach((id) => {
        deleteMockTask(id)
        deletedIds.add(id)
      })

      if (runIds.length && isPublicDemo) {
        failures.push('公开演示版不能删除真实研究任务')
      } else {
        const outcomes = await Promise.allSettled(
          runIds.map((id) => workflowApi.deleteRun(id)),
        )
        outcomes.forEach((outcome, index) => {
          if (outcome.status === 'fulfilled') deletedIds.add(runIds[index])
          else failures.push(`${sidebarItems.find((item) => item.id === runIds[index])?.title ?? runIds[index]}：删除失败`)
        })
      }

      for (const project of listProjects()) {
        if (!project.taskIds.some((id) => deletedIds.has(id))) continue
        updateProject(project.id, {
          taskIds: project.taskIds.filter((id) => !deletedIds.has(id)),
        })
      }

      setMockTasks(listMockTasks())
      setProjects(listProjects())
      if (!isPublicDemo) setRuns(await workflowApi.listRuns())
      else setRuns((current) => current.filter((item) => !deletedIds.has(item.id)))

      return { deletedIds, failures }
    })

    if (!result) return false
    if (taskId && result.deletedIds.has(taskId)) {
      runIdRef.current = null
      setRun(null)
      setMockTask(null)
      setBaselineRun(null)
      changeView({ kind: 'new' })
    }
    if (result.failures.length) {
      setError(`部分任务未删除：${result.failures.join('；')}`)
      return false
    }
    return true
  }

  async function deleteProjects(projectIds: string[]): Promise<boolean> {
    const availableProjects = listProjects()
    const availableIds = new Set(availableProjects.map((project) => project.id))
    const uniqueIds = [...new Set(projectIds)].filter((id) => availableIds.has(id))
    if (!uniqueIds.length) return false

    const confirmed = window.confirm(
      `确定删除已选择的 ${uniqueIds.length} 个项目吗？项目中的研究任务和本地数据文件将保留，可在任务列表中继续访问。`,
    )
    if (!confirmed) return false

    const deleted = removeProjects(uniqueIds)
    if (!deleted) return false
    const nextProjects = listProjects()
    setProjects(nextProjects)
    const activeId = isProjectView(view) ? view.id : null
    if (activeId && uniqueIds.includes(activeId)) {
      changeView({ kind: 'projects' })
    }
    return true
  }

  async function decideGate(gate: string, input: GateDecisionInput) {
    if (!run) return
    const label = gate === 'H1'
      ? '正在确认研究边界并生成候选方案…'
      : gate === 'H2'
        ? '正在冻结所选研究合同、执行并独立复现…'
        : gate === 'H3'
          ? '正在按授权结论生成完整论文初稿…'
          : '正在封存 H4 已批准的最终初稿…'
    const nextRun = await withBusy(label, () => workflowApi.decideGate(run, gate, input))
    if (!nextRun) return
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns()
  }

  async function retryWriting() {
    if (!run) return
    const nextRun = await withBusy('正在使用已封存的回归结果重新生成完整论文初稿…', () => workflowApi.retryWriting(run.id))
    if (!nextRun) return
    runIdRef.current = nextRun.id
    setRun(nextRun)
    await refreshRuns()
  }

  async function submitGateRevision(gate: 'H1' | 'H2', revision: unknown, comment: string) {
    if (!run) return
    setBusy(true)
    setBusyLabel(`正在提交 ${gate} 修订并重新校验…`)
    setError(null)
    let returnedRun = run
    try {
      if (run.status === 'waiting_human') {
        returnedRun = await workflowApi.decideGate(run, gate, { action: 'revise', comment })
        runIdRef.current = returnedRun.id
        setRun(returnedRun)
      }
      const nextRun = await workflowApi.submitRevision(returnedRun, gate, revision)
      runIdRef.current = nextRun.id
      setRun(nextRun)
      await refreshRuns()
    } catch (reason) {
      runIdRef.current = returnedRun.id
      setRun(returnedRun)
      setError(reason instanceof Error ? reason.message : String(reason))
      await refreshRuns().catch(() => undefined)
    } finally {
      setBusy(false)
      setBusyLabel('')
    }
  }

  async function saveConfig(input: RuntimeConfigUpdate): Promise<boolean> {
    const nextConfig = await withBusy('正在安全保存后端配置…', () => workflowApi.updateRuntimeConfig(input))
    if (!nextConfig) {
      setAccessTokenVerified(false)
      return false
    }
    setConfig(nextConfig)
    setAccessTokenVerified(workflowApi.hasAccessToken())
    return true
  }

  async function testConnection(target: ConnectionTestResult['target']) {
    const result = await withBusy(`正在测试${target === 'qwen' ? '千问模型' : '研究执行器'}连接…`, () => workflowApi.testRuntimeConnection(target))
    return result ?? { target, success: false, message: '连接测试未完成。' }
  }

  if (loading) return <main className="load-state"><span className="loading-mark" /><strong>正在连接代码工作流</strong><p>读取流程定义、配置状态与持久化运行记录…</p></main>

  const activeRealRun = view.kind === 'task' && !isMockTaskId(view.id) ? run : null
  const activeProjectId = isProjectView(view) ? view.id : getSelectedProjectId()
  const activeProject = activeProjectId ? getProject(activeProjectId) : null
  const isShowcaseReplay = activeProject?.id === SHOWCASE_PROJECT_ID
    && activeProject.status !== 'handoff_ready'
  const sidebarItemsForDisplay = isShowcaseReplay
    ? sidebarItems.filter((item) => item.id !== SHOWCASE_TASK_ID)
    : sidebarItems
  const caseReady = Boolean(draft.case.datasetRefs.length
    && (!activeRealRun || draft.case.caseId === activeRealRun.caseId)
    && (!baselineRun || draft.case.caseId === baselineRun.caseId))
  const pendingReviewTask = sidebarItems.find((item) => item.status === 'waiting_human')
  const activeTaskTitle = mockTask?.title
    ?? (activeRealRun ? displayResearchTitle(activeRealRun.caseSubmission?.researchQuestion ?? activeRealRun.caseName) : undefined)

  const toolbarTitle = view.kind === 'new'
    ? '新研究'
    : view.kind === 'projects'
      ? '项目'
      : view.kind === 'project'
        ? activeProject?.title ?? '项目总览'
        : view.kind === 'discovery'
          ? DISCOVERY_STEP_LABELS[view.step]
          : view.kind === 'library'
            ? LIBRARY_LABELS[view.resourceKind]
          : view.kind === 'reader'
            ? 'AI 读论文'
      : view.kind === 'settings'
        ? '设置'
        : activeTaskTitle ?? '任务'
  const toolbarSubtitle = view.kind === 'discovery'
    ? `${activeProject?.title ?? '研究发现'} · ${isPublicDemo
      ? '公开界面演示'
      : isShowcaseReplay
        ? '知识服务 + Qwen 研究引擎'
        : '知识服务 + Group1 发现引擎'}`
    : view.kind === 'library'
      ? view.resourceKind === 'literature' ? '找论文、读全文，并把证据加入当前项目' : '研究资源检索与项目资料管理'
      : view.kind === 'reader'
        ? '全文阅读 · AI 辅助理解 · 证据定位'
      : view.kind === 'project'
        ? '研究发现与正式任务进度'
    : view.kind === 'task'
    ? mockTask
      ? `${mockTask.currentGate ? `${mockTask.currentGate} · ` : ''}研究进行中`
      : activeRealRun
        ? activeRealRun.currentGate ? `${activeRealRun.currentGate} · 等待人工确认` : '研究进行中'
        : undefined
    : undefined

  return (
    <div className={`shell theme-${theme} ${collapsed ? 'is-collapsed' : ''} ${drawerOpen ? 'is-drawer-open' : ''}`}>
      <AppSidebar
        nav={view.kind === 'new' || view.kind === 'projects' || view.kind === 'settings'
          ? view.kind
          : view.kind === 'library' || view.kind === 'reader'
            ? 'library'
            : null}
        activeTaskId={taskId}
        activeProjectId={activeProjectId}
        projects={projects.map((project) => ({
          id: project.id,
          title: project.title,
          statusText: project.status === 'handoff_ready'
            ? '可交接'
            : project.status === 'archived'
              ? '已归档'
              : project.discovery.completedSteps.includes(6)
                ? '发现完成'
                : `发现 ${new Set(project.discovery.completedSteps).size}/6`,
          updatedAt: project.updatedAt,
        }))}
        tasks={sidebarItemsForDisplay.map((item) => item.id === activeRealRun?.id ? { ...item, title: activeTaskTitle ?? item.title, meta: '研究任务' } : item)}
        pendingReviewCount={sidebarItemsForDisplay.filter((item) => item.status === 'waiting_human').length}
        config={config}
        theme={theme}
        collapsed={collapsed}
        onToggleCollapse={toggleCollapse}
        onToggleTheme={() => setTheme(toggleTheme())}
        onNavigate={navigate}
        onOpenProject={openProject}
        onOpenTask={openTask}
        onDeleteProjects={deleteProjects}
        onDeleteTasks={deleteTasks}
        onOpenPendingReview={() => { if (pendingReviewTask) openTask(pendingReviewTask.id) }}
      />
      {drawerOpen && <button type="button" className="shell__scrim" aria-label="关闭侧边栏" onClick={() => setDrawerOpen(false)} />}
      <main className="shell-main">
        <MainToolbar title={toolbarTitle} subtitle={toolbarSubtitle} onToggleSidebar={toggleMobileSidebar}>
          {view.kind === 'task' && (mockTask || activeRealRun) && (
            <>
              <button type="button" className="secondary-button" onClick={() => setWorkspaceOpen(true)}><FileStack size={14} />证据与文件</button>
              {mockTask && <button type="button" className="quiet-button" onClick={handleDeleteMockTask}><Trash2 size={14} />删除</button>}
              {activeRealRun && <button type="button" className="quiet-button" disabled={busy} onClick={() => void deleteRun()}><Trash2 size={14} />删除</button>}
            </>
          )}
        </MainToolbar>
        {error && <div className="error-banner" role="alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>关闭</button></div>}

        {view.kind === 'settings' && (
          <div className="shell-view">
            <SystemConfigPanel status={config} accessTokenPresent={accessTokenPresent} accessTokenVerified={accessTokenVerified} busy={busy} onRefresh={() => withBusy('正在重新读取配置状态…', refreshConfig).then(() => undefined)} onSetAccessToken={(token) => { workflowApi.setAccessToken(token); setAccessTokenPresent(workflowApi.hasAccessToken()); setAccessTokenVerified(false) }} onSave={saveConfig} onTest={testConnection} />
          </div>
        )}
        {view.kind === 'projects' && (
          <div className="shell-view shell-view--scroll">
            <ProjectsPage
              onCreateProject={() => navigate('new')}
              onOpenProject={openProject}
              onOpenDiscovery={openDiscovery}
              onDeleteProjects={deleteProjects}
            />
          </div>
        )}
        {view.kind === 'project' && (
          <div className="shell-view shell-view--scroll">
            <ProjectOverviewPage
              projectId={view.id}
              onOpenProjects={() => navigate('projects')}
              onOpenDiscovery={openDiscovery}
              onOpenLibrary={openLibrary}
              onOpenTask={openTask}
            />
          </div>
        )}
        {view.kind === 'discovery' && (
          <div className="shell-view shell-view--scroll">
            <DiscoveryPage
              projectId={view.id}
              step={view.step}
              onChangeStep={openDiscovery}
              onOpenOverview={openProject}
              onOpenLibrary={openLibrary}
              onCreateDemoTask={(handoff) => handleCreateDemoTask(view.id, handoff)}
              onLaunchRun={(nextRun) => void openLaunchedDiscoveryRun(nextRun)}
              publicDemo={isPublicDemo}
            />
          </div>
        )}
        {view.kind === 'library' && (
          <div className="shell-view">
            <ResourceLibraryPage
              kind={view.resourceKind}
              activeProjectId={activeProjectId}
              onKindChange={openLibrary}
              onOpenProject={openProject}
              onOpenReader={openLiteratureReader}
            />
          </div>
        )}
        {view.kind === 'reader' && (
          <div className="shell-view">
            <LiteratureReaderPage
              resourceId={view.id}
              activeProjectId={activeProjectId}
              onBack={() => openLibrary('literature')}
            />
          </div>
        )}
        {view.kind === 'new' && !showPreflight && !showAdvancedInput && (
          <div className="shell-view">
            <TaskComposer
              config={config}
              group1Bundle={group1Bundle}
              publicDemo={isPublicDemo}
              importReport={importReport}
              busy={busy}
              busyLabel={busyLabel}
              onImportCaseFolder={importCaseFolder}
              onImportGroup1Handoff={importGroup1Handoff}
              onStartVerifiedGroup1Bundle={startVerifiedGroup1Bundle}
              onOpenAdvanced={() => setShowAdvancedInput(true)}
              onOpenSettings={() => navigate('settings')}
              onCreateProject={handleCreateProject}
            />
          </div>
        )}
        {view.kind === 'new' && !showPreflight && showAdvancedInput && (
          <div className="shell-view shell-view--scroll">
            <ResearchInputForm draft={draft} config={config} importReport={importReport} busy={busy} onChange={setDraft} onLoadDemo={() => { setDraft(demoResearchDraft()); setImportReport(null) }} onImportCaseFile={(file) => importCaseFile(file, 'hypoweaver')} onOpenSettings={() => navigate('settings')} onCheck={() => setShowPreflight(true)} />
          </div>
        )}
        {view.kind === 'new' && showPreflight && (
          <div className="shell-view shell-view--scroll">
            <PreflightPanel draft={draft} items={preflightItems} importReport={importReport} busy={busy} onBack={() => setShowPreflight(false)} onStart={startResearch} />
          </div>
        )}
        {view.kind === 'task' && mockTask && (
          <div className="shell-view">
            <div className="task-workspace">
              <MockTaskStream task={mockTask} onGateDecision={handleMockGate} onOpenDrawer={() => setWorkspaceOpen(true)} />
              <TaskResearchRail mockTask={mockTask} onOpenDrawer={() => setWorkspaceOpen(true)} />
            </div>
          </div>
        )}
        {view.kind === 'task' && !mockTask && activeRealRun && definition && (
          <div className="shell-view">
            <div className="task-workspace">
              <RunTaskStream
                definition={definition}
                run={activeRealRun}
                busy={busy}
                busyLabel={busyLabel}
                onGateDecision={decideGate}
                onSubmitRevision={submitGateRevision}
                onRetryWriting={retryWriting}
                onOpenDrawer={() => setWorkspaceOpen(true)}
              />
              <TaskResearchRail run={activeRealRun} onOpenDrawer={() => setWorkspaceOpen(true)} />
            </div>
          </div>
        )}
        {view.kind === 'task' && !mockTask && !activeRealRun && (
          <div className="shell-view">
            <div className="stream__status" style={{ margin: 'auto' }}>{busy ? (busyLabel || '正在加载任务…') : '找不到这个任务，可能已被删除。'}</div>
          </div>
        )}
      </main>

      <WorkspaceDrawer
        open={workspaceOpen}
        onClose={() => setWorkspaceOpen(false)}
        caseName={activeTaskTitle ?? ''}
        definition={definition}
        run={activeRealRun}
        baselineRun={baselineRun}
        busy={busy}
        caseReady={caseReady}
        onStartBaseline={activeRealRun ? () => startBaseline() : undefined}
        mockTask={mockTask}
      />
    </div>
  )
}
