/**
 * Mock 全流程管线：把「任务理解 → 文献调研 → 假设生成」这段尚未接入真实后端的
 * 前半程，与 H1–H4 的后半程串成一条完整演示流。
 * - 状态持久化到 localStorage（hw-mock-tasks），刷新后可恢复。
 * - subscribeMockTask 用定时器逐句吐出 transcript，遇到闸门暂停等待人工决策。
 * - 全部为演示数据，不触碰任何后端；接真实后端时只需替换 TaskStream 的数据源。
 */

export type MockGate = 'H1' | 'H2' | 'H3' | 'H4'
export type MockMode = 'discovery_blind' | 'reproduction_aligned'
export type MockStageStatus = 'pending' | 'running' | 'waiting_gate' | 'done' | 'skipped'
export type MockGateAction = 'approve' | 'revise' | 'reject'

export interface MockArtifact {
  id: string
  name: string
  kind: 'figure' | 'table' | 'document' | 'data'
  note: string
}

export interface MockStage {
  key: string
  label: string
  eyebrow: string
  gate?: MockGate
  gateTitle?: string
  gateHint?: string
  lines: string[]
  artifacts: MockArtifact[]
  /** 运行时状态 */
  status: MockStageStatus
  revealed: number
  gateDecision?: MockGateAction
  gateComment?: string
}

export interface MockTask {
  id: string
  title: string
  mode: MockMode
  status: 'running' | 'waiting_human' | 'completed' | 'rejected'
  currentGate?: MockGate
  createdAt: string
  updatedAt: string
  /** 上次推进时刻：按真实流逝时间补齐进度，后台标签页节流也不会卡住 */
  progressAt?: string
  stages: MockStage[]
}

export interface MockTaskSummary {
  id: string
  title: string
  mode: MockMode
  status: MockTask['status']
  currentGate?: MockGate
  updatedAt: string
}

export const MOCK_TASK_STORE_KEY = 'hw-mock-tasks'
export const MOCK_TASK_STORE_VERSION = 1 as const
export const MAX_LOCAL_DEMO_TASKS = 100
const TICK_MS = 950

interface MockTaskStore {
  version: typeof MOCK_TASK_STORE_VERSION
  tasks: MockTask[]
}

type StageScript = Omit<MockStage, 'status' | 'revealed' | 'gateDecision' | 'gateComment'>

/** 绿色金融示例剧本：11 个阶段，覆盖完整科研流程。 */
const SCRIPT: StageScript[] = [
  {
    key: 'task_understanding', label: '任务理解', eyebrow: 'Stage 01 · 前半程（演示）',
    lines: [
      '解析研究任务描述，识别研究领域：绿色金融 × 企业环境行为。',
      '抽取研究对象：地级市绿色信贷投放与高污染企业转型。',
      '确认研究类型：政策评估（准自然实验），目标估计量为处理效应。',
      '生成任务卡：研究窗口 2012–2022，分析单位为企业-年份面板。',
    ],
    artifacts: [{ id: 'a-task-card', name: 'task_card.json', kind: 'document', note: '任务理解卡片 · 演示数据' }],
  },
  {
    key: 'literature', label: '文献调研', eyebrow: 'Stage 02 · 前半程（演示）',
    lines: [
      '检索绿色信贷政策相关文献 128 篇，筛除综述与非实证研究后剩 41 篇。',
      '归纳主流识别策略：DID（23 篇）、三重差分（8 篇）、断点回归（4 篇）。',
      '定位研究缺口：现有研究少有区分「主动转型」与「被动收缩」两条机制。',
      '构建引文清单与证据地图，标注可复用的变量定义 17 条。',
    ],
    artifacts: [
      { id: 'a-lit-map', name: 'literature_map.csv', kind: 'table', note: '41 篇文献证据地图 · 演示数据' },
      { id: 'a-lit-note', name: 'gap_analysis.md', kind: 'document', note: '研究缺口备忘 · 演示数据' },
    ],
  },
  {
    key: 'hypothesis', label: '假设生成', eyebrow: 'Stage 03 · 前半程（演示）',
    lines: [
      '基于任务卡与文献缺口生成候选假设 5 条，按可检验性排序。',
      'H-a：绿色信贷约束显著降低高污染企业的新增授信规模（方向：负）。',
      'H-b：受约束企业的绿色专利产出上升，存在「倒逼创新」机制（方向：正）。',
      '为每条假设标注所需变量、预期符号与潜在混杂因素。',
      '假设包已就绪，进入案例接入与 H1 边界确认。',
    ],
    artifacts: [{ id: 'a-hypo', name: 'hypothesis_pack.json', kind: 'document', note: '候选假设包 · 演示数据' }],
  },
  {
    key: 'intake_h1', label: '案例接入与边界确认', eyebrow: 'Stage 04 · H1 人工闸门',
    gate: 'H1', gateTitle: 'H1 · 请确认研究边界', gateHint: '批准后系统才会拆解假设并设计方法；退回可修改研究问题与变量定义。',
    lines: [
      '规范化 CaseSubmission：研究问题、假设、变量定义与数据引用完成绑定。',
      '安全校验通过：未发现隐藏参考材料或已发表结果泄漏。',
      '输入校验通过：主数据 24,318 行 × 37 列，样本期 2012–2022。',
      '流程已暂停，等待人工确认研究边界（H1）。',
    ],
    artifacts: [{ id: 'a-case', name: 'case_submission.json', kind: 'document', note: '规范化案例包 · 演示数据' }],
  },
  {
    key: 'understanding', label: '研究理解', eyebrow: 'Stage 05 · 假设拆解与数据画像',
    lines: [
      '假设拆解：H-a / H-b 拆分为 4 条可检验命题，绑定变量角色。',
      '数据画像：面板平衡度 91.4%，缺失集中在 2012–2013 年环保投资字段。',
      '方法路由：识别为政策-因果类问题，候选方法族 policy_causal。',
    ],
    artifacts: [{ id: 'a-profile', name: 'data_profile.json', kind: 'data', note: '数据画像 · 演示数据' }],
  },
  {
    key: 'design', label: '方法设计', eyebrow: 'Stage 06 · 三策略候选',
    lines: [
      '生成候选设计 3 份：直接基准（TWFE-DID）、识别优先（事件研究）、测量稳健性优先。',
      '每份候选执行 Probe 干跑：语法与数据可达性检查全部通过，未读取任何统计结果。',
      '候选设计集已封装，交由四类独立 Reviewer 审查。',
    ],
    artifacts: [{ id: 'a-designs', name: 'candidate_designs.json', kind: 'document', note: '三份候选设计 · 演示数据' }],
  },
  {
    key: 'review_h2', label: '独立审查与方法冻结', eyebrow: 'Stage 07 · H2 人工闸门',
    gate: 'H2', gateTitle: 'H2 · 请选择并冻结分析计划', gateHint: 'Reviewer 只淘汰硬失败方案；批准后方法即冻结，执行前不可再看结果改设计。',
    lines: [
      '测量 / 因果 / 统计 / 复现 四类 Reviewer 并行审查完毕。',
      '「识别优先」候选存在 1 个 critical 问题（平行趋势前置检验缺失），已标记不可冻结。',
      '可行候选 2 份：直接基准（推荐）、测量稳健性优先。',
      '流程已暂停，等待人工选择候选并冻结正式研究合同（H2）。',
    ],
    artifacts: [{ id: 'a-critic', name: 'critic_reports.json', kind: 'document', note: '四类审查报告 · 演示数据' }],
  },
  {
    key: 'execution', label: '实验执行与独立复现', eyebrow: 'Stage 08 · 冻结合同执行',
    lines: [
      '按冻结合同执行 TWFE-DID 基准回归与事件研究图。',
      '基准估计：处理组新增授信下降 12.7%（SE 3.1%，p<0.01）· 演示数据。',
      '独立复现器以 NumPy 重算主结果，数值容差 1e-6 内一致。',
      '安慰剂检验 500 次置换，真实估计位于置换分布 0.4% 分位。',
    ],
    artifacts: [
      { id: 'a-reg', name: 'baseline_regression.csv', kind: 'table', note: '基准回归表 · 演示数据' },
      { id: 'a-event', name: 'event_study.png', kind: 'figure', note: '事件研究图 · 演示数据' },
    ],
  },
  {
    key: 'audit_h3', label: '证据审计与结论授权', eyebrow: 'Stage 09 · H3 人工闸门',
    gate: 'H3', gateTitle: 'H3 · 请逐条授权结论', gateHint: 'Writer 只能读取本次明确授权的结论；可对每条结论批准、降级或拒绝。',
    lines: [
      '证据图生成完毕：主效应、动态效应与安慰剂三组图。',
      '证据评估 + 科学审计：候选 Claim 3 条，其中 1 条建议降级为关联表述。',
      '确定性 Claim Gate 完成准入判定：2 条可批准、1 条须降级。',
      '流程已暂停，等待人工逐条授权结论（H3）。',
    ],
    artifacts: [{ id: 'a-claims', name: 'claim_ledger.json', kind: 'document', note: 'Claim 台账 · 演示数据' }],
  },
  {
    key: 'writing_h4', label: '论文写作与终稿审核', eyebrow: 'Stage 10 · H4 人工闸门',
    gate: 'H4', gateTitle: 'H4 · 请审核最终论文初稿', gateHint: '一致性审计已通过；批准后成果封存，退回可指定章节重写。',
    lines: [
      '按授权结论生成论文图 4 张，绑定 Execution 与 Claim 来源。',
      'Scientific Writer 完成 8 节初稿，统计事实由代码注入，禁止虚构引用。',
      '一致性审计通过：全文 6,842 字，无未授权因果表述。',
      '流程已暂停，等待人工审核最终稿（H4）。',
    ],
    artifacts: [
      { id: 'a-paper', name: 'manuscript_draft.md', kind: 'document', note: '论文初稿 8 节 · 演示数据' },
      { id: 'a-figs', name: 'publication_figures/', kind: 'figure', note: '论文图 4 张 · 演示数据' },
    ],
  },
  {
    key: 'sealing', label: '成果封存', eyebrow: 'Stage 11 · 不可变成果包',
    lines: [
      '计算 HMAC 封存哈希，打包研究计划、执行结果、Claim 台账与论文。',
      '成果包已封存，可进入盲测评估与六系统比较。本任务全程为演示数据。',
    ],
    artifacts: [{ id: 'a-seal', name: 'sealed_bundle.hmac', kind: 'data', note: '封存成果包 · 演示数据' }],
  },
]

/** mock H2 的候选设计（供闸门卡片展示） */
export const MOCK_H2_CANDIDATES = [
  { id: 'direct_baseline', label: '直接基准 · TWFE-DID', detail: 'Probe pass · Reviewer 问题 0 · 推荐', recommended: true },
  { id: 'measurement_robustness', label: '测量稳健性优先', detail: 'Probe pass · Reviewer 问题 1（非 critical）', recommended: true },
  { id: 'identification_first', label: '识别优先 · 事件研究', detail: 'critical：平行趋势前置检验缺失 · 不可冻结', recommended: false },
]

/** mock H3 的候选结论（供闸门卡片展示） */
export const MOCK_H3_CLAIMS = [
  { id: 'claim-1', text: '绿色信贷约束使高污染企业新增授信显著下降（演示数据）。', admission: '已准入', permitted: ['approve', 'reject'] as const },
  { id: 'claim-2', text: '受约束企业绿色专利产出显著上升，存在倒逼创新机制（演示数据）。', admission: '已准入', permitted: ['approve', 'reject'] as const },
  { id: 'claim-3', text: '约束效应主要由被动收缩驱动——须降级为关联表述（演示数据）。', admission: '必须降级', permitted: ['approve', 'reject'] as const },
]

function nowIso(): string {
  return new Date().toISOString()
}

function loadAll(): MockTask[] {
  try {
    const raw = localStorage.getItem(MOCK_TASK_STORE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (Array.isArray(parsed)) {
      const tasks = parsed as MockTask[]
      saveAll(tasks)
      return tasks
    }
    if (
      parsed
      && typeof parsed === 'object'
      && Array.isArray((parsed as Partial<MockTaskStore>).tasks)
    ) {
      const store = parsed as Partial<MockTaskStore>
      const tasks = store.tasks as MockTask[]
      if (store.version !== MOCK_TASK_STORE_VERSION) saveAll(tasks)
      return tasks
    }
    return []
  } catch {
    return []
  }
}

function saveAll(tasks: MockTask[]): void {
  const store: MockTaskStore = {
    version: MOCK_TASK_STORE_VERSION,
    tasks,
  }
  localStorage.setItem(MOCK_TASK_STORE_KEY, JSON.stringify(store))
}

type Listener = () => void
const listeners = new Set<Listener>()

function notify(): void {
  listeners.forEach((listener) => listener())
}

/** 订阅 mock 任务集合的任何变化（侧边栏任务列表用）。 */
export function subscribeMockTasks(listener: Listener): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function listMockTasks(): MockTaskSummary[] {
  return loadAll()
    .map(({ id, title, mode, status, currentGate, updatedAt }) => ({ id, title, mode, status, currentGate, updatedAt }))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export function getMockTask(id: string): MockTask | null {
  return loadAll().find((task) => task.id === id) ?? null
}

export function isMockTaskId(id: string): boolean {
  return id.startsWith('mock-')
}

export function createMockTask(prompt: string, mode: MockMode): MockTask {
  const tasks = loadAll()
  if (tasks.length >= MAX_LOCAL_DEMO_TASKS) {
    throw new Error(`本地演示任务已达到 ${MAX_LOCAL_DEMO_TASKS} 个上限；请先删除不再需要的演示任务。`)
  }
  const title = prompt.trim().replace(/\s+/g, ' ').slice(0, 42) || '未命名研究任务'
  const task: MockTask = {
    id: `mock-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    title,
    mode,
    status: 'running',
    createdAt: nowIso(),
    updatedAt: nowIso(),
    progressAt: nowIso(),
    stages: SCRIPT.map((stage, index) => ({
      ...stage,
      artifacts: stage.artifacts.map((artifact) => ({ ...artifact })),
      status: index === 0 ? 'running' : 'pending',
      revealed: 0,
    })),
  }
  tasks.push(task)
  saveAll(tasks)
  notify()
  return task
}

export function deleteMockTask(id: string): void {
  saveAll(loadAll().filter((task) => task.id !== id))
  notify()
}

/** 状态机：推进一格（吐一句 / 结束一个阶段 / 停在闸门）。返回是否发生变化。 */
function advance(task: MockTask): boolean {
  if (task.status === 'completed' || task.status === 'rejected' || task.status === 'waiting_human') return false
  const index = task.stages.findIndex((stage) => stage.status === 'running')
  if (index === -1) return false
  const stage = task.stages[index]
  if (stage.revealed < stage.lines.length) {
    stage.revealed += 1
  } else if (stage.gate && !stage.gateDecision) {
    stage.status = 'waiting_gate'
    task.status = 'waiting_human'
    task.currentGate = stage.gate
  } else {
    stage.status = 'done'
    const next = task.stages[index + 1]
    if (next) {
      next.status = 'running'
    } else {
      task.status = 'completed'
    }
  }
  task.updatedAt = nowIso()
  return true
}

/** 按真实流逝时间补齐推进：隐藏标签页定时器被节流时，回到前台一次性追上。 */
function advanceByTime(task: MockTask): boolean {
  const now = Date.now()
  const last = task.progressAt ? Date.parse(task.progressAt) : now - TICK_MS
  let steps = Math.min(Math.floor((now - last) / TICK_MS), 30)
  let changed = false
  while (steps > 0) {
    if (!advance(task)) break
    changed = true
    steps -= 1
  }
  if (changed) task.progressAt = new Date(now).toISOString()
  return changed
}

/** 闸门决策：approve 继续、revise 重播当前阶段、reject 终止。 */
export function decideMockGate(id: string, gate: MockGate, action: MockGateAction, comment?: string): MockTask | null {
  const tasks = loadAll()
  const task = tasks.find((item) => item.id === id)
  if (!task) return null
  const stage = task.stages.find((item) => item.gate === gate)
  if (!stage || stage.status !== 'waiting_gate') return null
  stage.gateComment = comment
  if (action === 'reject') {
    stage.gateDecision = 'reject'
    stage.status = 'done'
    task.status = 'rejected'
    task.currentGate = undefined
    task.stages.forEach((item) => { if (item.status === 'pending') item.status = 'skipped' })
  } else if (action === 'revise') {
    stage.gateDecision = undefined
    stage.revealed = 0
    stage.status = 'running'
    task.status = 'running'
    task.currentGate = undefined
  } else {
    stage.gateDecision = 'approve'
    stage.status = 'running' // 让状态机在下一 tick 收尾并进入下一阶段
    task.status = 'running'
    task.currentGate = undefined
  }
  task.progressAt = nowIso()
  task.updatedAt = nowIso()
  saveAll(tasks)
  notify()
  return task
}

/**
 * 订阅单个 mock 任务：内部起定时器逐句推进，组件卸载时取消。
 * 回调总是收到最新完整快照（含首帧）。
 */
export function subscribeMockTask(id: string, callback: (task: MockTask) => void): () => void {
  const current = getMockTask(id)
  if (current) callback(current)

  const tick = () => {
    const tasks = loadAll()
    const task = tasks.find((item) => item.id === id)
    if (!task) return
    if (advanceByTime(task)) {
      saveAll(tasks)
      callback(task)
      notify()
    }
  }
  const timer = window.setInterval(tick, TICK_MS)
  const onVisible = () => { if (document.visibilityState === 'visible') tick() }
  document.addEventListener('visibilitychange', onVisible)
  // 闸门决策等外部变化也要回流到订阅者
  const unsubscribe = subscribeMockTasks(() => {
    const task = getMockTask(id)
    if (task) callback(task)
  })
  return () => {
    window.clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisible)
    unsubscribe()
  }
}
