/**
 * 全流程展示快照：把已经完成的真实千问检索、公开数据执行、统计复算与 H1–H4
 * 串成一条稳定录屏流。快照不在演示时重复发起外部调用，全部数值来自封存结果。
 * - 状态持久化到 localStorage（hw-mock-tasks），刷新后可恢复。
 * - subscribeMockTask 用定时器逐句吐出 transcript，遇到闸门暂停等待人工决策。
 * - 新建的演示任务仍复用同一脚本；正式实时任务由 TaskStream 的后端数据源承载。
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
export const MOCK_TASK_STORE_VERSION = 5 as const
export const MAX_LOCAL_DEMO_TASKS = 100
export const SHOWCASE_TASK_ID = 'mock-carbon-market-showcase'
const TICK_MS = 950

interface MockTaskStore {
  version: typeof MOCK_TASK_STORE_VERSION
  tasks: MockTask[]
}

type StageScript = Omit<MockStage, 'status' | 'revealed' | 'gateDecision' | 'gateComment'>

/** 碳市场与高质量绿色创新真实研究快照：11 个阶段，覆盖完整科研流程。 */
const SCRIPT: StageScript[] = [
  {
    key: 'task_understanding', label: '任务理解', eyebrow: 'Stage 01 · 研究发现',
    lines: [
      '解析研究任务描述，识别研究领域：碳市场政策 × 企业高质量绿色技术创新。',
      '保留原始问题：全国碳排放权交易市场能否促进企业绿色发明创新。',
      '确认研究类型：企业面板政策评估；先由数据执行门决定可识别范围。',
      '生成任务卡：分析单位为企业—年度，政策暴露、创新质量与融资条件为核心构念。',
    ],
    artifacts: [{ id: 'a-task-card', name: 'task_card.json', kind: 'document', note: '任务理解卡片 · 冻结示范案例' }],
  },
  {
    key: 'literature', label: '文献调研', eyebrow: 'Stage 02 · 证据检索',
    lines: [
      '从本地知识库检索 12 个全文证据片段，来自 7 篇不同文献。',
      '检索多样性门将每篇文献上限设为 2 个片段，跳过 35 个超限候选片段。',
      '定位研究缺口：既有研究较少同时区分绿色发明质量、融资条件与动态路径。',
      'Qwen3.7-plus 完成研究规划和问题—计划一致性审查，2 次调用均成功。',
    ],
    artifacts: [
      { id: 'a-lit-map', name: 'evidence_bundle.json', kind: 'table', note: '12 个片段 · 7 篇文献 · 哈希封存' },
      { id: 'a-lit-note', name: 'gap_analysis.md', kind: 'document', note: '研究趋势与空白分析' },
    ],
  },
  {
    key: 'hypothesis', label: '假设生成', eyebrow: 'Stage 03 · 空白与假设',
    lines: [
      '基于任务卡与证据束生成主效应、融资机制和竞争异质性三组可证伪假设。',
      'H1：碳政策暴露与企业绿色发明专利申请增加相一致。',
      'H2：融资约束代理值下降与政策促进长期绿色研发的机制方向一致。',
      'H3：政策暴露与绿色创新之间的关系随行业竞争程度变化。',
      '假设包已就绪，进入案例接入与 H1 边界确认。',
    ],
    artifacts: [{ id: 'a-hypo', name: 'hypothesis_pack.json', kind: 'document', note: '候选假设与机制图谱' }],
  },
  {
    key: 'intake_h1', label: '案例接入与边界确认', eyebrow: 'Stage 04 · H1 人工闸门',
    gate: 'H1', gateTitle: 'H1 · 请确认研究边界', gateHint: '批准后系统才会拆解假设并设计方法；退回可修改研究问题与变量定义。',
    lines: [
      '规范化研究输入：原始问题、三组假设、证据束和两个公开数据候选完成绑定。',
      '数据门发现：公开许可面板止于 2021 年，全国市场结果期不足。',
      '自适应范围确认：保持理论链不变，本轮执行区域碳政策公开复现，全国命题进入后续扩展。',
      '流程已暂停，等待人工确认研究边界（H1）。',
    ],
    artifacts: [{ id: 'a-case', name: 'case_submission.json', kind: 'document', note: '规范化研究输入包' }],
  },
  {
    key: 'understanding', label: '研究理解', eyebrow: 'Stage 05 · 假设拆解与数据画像',
    lines: [
      '假设拆解：主效应、融资约束机制与竞争异质性绑定到具体字段。',
      '数据画像：14,208 条原始观测、1,184 家企业、2010—2021 年 12 期平衡面板。',
      '异常识别：75 家企业存在政策暴露 1→0 回退，进入动态分析的样本规则。',
    ],
    artifacts: [{ id: 'a-profile', name: 'data_profile.json', kind: 'data', note: '数据画像与连接诊断' }],
  },
  {
    key: 'design', label: '方法设计', eyebrow: 'Stage 06 · 三策略候选',
    lines: [
      '生成候选设计 3 份：当期暴露双向固定效应、单调路径事件研究、全国市场等待数据方案。',
      '每份候选执行 Probe 干跑：语法与数据可达性检查全部通过，未读取任何统计结果。',
      '候选设计集已封装，交由四类独立 Reviewer 审查。',
    ],
    artifacts: [{ id: 'a-designs', name: 'candidate_designs.json', kind: 'document', note: '三份可执行候选设计' }],
  },
  {
    key: 'review_h2', label: '独立审查与方法冻结', eyebrow: 'Stage 07 · H2 人工闸门',
    gate: 'H2', gateTitle: 'H2 · 请选择并冻结分析计划', gateHint: 'Reviewer 只淘汰硬失败方案；批准后方法即冻结，执行前不可再看结果改设计。',
    lines: [
      '测量 / 因果 / 统计 / 复现 四类 Reviewer 并行审查完毕。',
      '「全国市场直接 DID」因缺少 2022 年以后结果和官方企业名单被标记为不可冻结。',
      '可行方案：区域公开复现主模型 + 单调路径事件研究 + 企业轨迹置换。',
      '流程已暂停，等待人工选择候选并冻结正式研究合同（H2）。',
    ],
    artifacts: [{ id: 'a-critic', name: 'critic_reports.json', kind: 'document', note: '四类独立审查报告' }],
  },
  {
    key: 'execution', label: '实验执行与独立复现', eyebrow: 'Stage 08 · 冻结合同执行',
    lines: [
      '按冻结合同执行企业与年份固定效应、事件研究、七项稳健性和机制/异质性诊断。',
      '14,196 条企业—年份观测的主系数为 0.0717（聚类 SE 0.0204，p=0.00043）。',
      '独立复算器以 NumPy 重算全部核心结果，16/16 项核验通过，最大系数差小于 5×10⁻¹¹。',
      '政策前联合检验 p=0.494；499 次企业轨迹置换的双侧 p=0.004。',
    ],
    artifacts: [
      { id: 'a-reg', name: 'baseline_regression.csv', kind: 'table', note: '主回归与稳健性结果' },
      { id: 'a-event', name: 'event_study.png', kind: 'figure', note: '动态效应与平行趋势图' },
    ],
  },
  {
    key: 'audit_h3', label: '证据审计与结论授权', eyebrow: 'Stage 09 · H3 人工闸门',
    gate: 'H3', gateTitle: 'H3 · 请逐条授权结论', gateHint: 'Writer 只能读取本次明确授权的结论；可对每条结论批准、降级或拒绝。',
    lines: [
      '证据图生成完毕：理论机制、动态效应与八模型比较三组期刊风格图。',
      '证据评估：区域公开复现、前趋势和融资约束方向可报告；竞争异质性未获支持。',
      'Claim Gate 将全国市场因果命题保留为后续确认性研究，不与当前区域结果混写。',
      '流程已暂停，等待人工逐条授权结论（H3）。',
    ],
    artifacts: [{ id: 'a-claims', name: 'claim_ledger.json', kind: 'document', note: '结论—证据映射台账' }],
  },
  {
    key: 'writing_h4', label: '论文写作与终稿审核', eyebrow: 'Stage 10 · H4 人工闸门',
    gate: 'H4', gateTitle: 'H4 · 请审核最终论文初稿', gateHint: '一致性审计已通过；批准后成果封存，退回可指定章节重写。',
    lines: [
      '按授权结论生成 3 张黑白期刊图与 4 组研究表，逐项绑定结果和数据来源。',
      'Scientific Writer 完成 6 节正式论文初稿，统计事实由封存结果注入。',
      '一致性审计通过：摘要、正文、表格、图注与 Claim 台账口径一致。',
      '流程已暂停，等待人工审核最终稿（H4）。',
    ],
    artifacts: [
      { id: 'a-paper', name: 'manuscript_draft.md', kind: 'document', note: '完整研究报告初稿（6 节）' },
      { id: 'a-figs', name: 'publication_figures/', kind: 'figure', note: 'PNG / SVG / PDF 期刊图 3 张' },
    ],
  },
  {
    key: 'sealing', label: '成果封存', eyebrow: 'Stage 11 · 不可变成果包',
    lines: [
      '计算 SHA-256，索引两轮协议、执行结果、独立复算、Claim 台账与论文。',
      '23 项可提交材料完成索引；本地知识库原文与分析数据按授权范围保持内部存储。',
    ],
    artifacts: [{ id: 'a-seal', name: 'sealed_bundle.hmac', kind: 'data', note: '不可变成果包与审计清单' }],
  },
]

/** mock H2 的候选设计（供闸门卡片展示） */
export const MOCK_H2_CANDIDATES = [
  { id: 'regional_replication', label: '区域公开复现组合设计', detail: '企业/年份 FE + 动态诊断 + 轨迹置换 · 推荐', recommended: true },
  { id: 'monotone_event', label: '单调路径事件研究', detail: 'Probe pass · 作为趋势与动态模式诊断', recommended: true },
  { id: 'national_direct', label: '全国市场直接 DID', detail: 'critical：缺少2022年以后结果与官方企业绑定', recommended: false },
]

/** mock H3 的候选结论（供闸门卡片展示） */
export const MOCK_H3_CLAIMS = [
  { id: 'claim-1', text: '在公开复现样本及原数据政策暴露编码下，碳政策暴露与绿色发明专利申请呈稳定正向关系。', admission: '已准入', permitted: ['approve', 'reject'] as const },
  { id: 'claim-2', text: '政策暴露前动态系数整体不显著，联合检验未拒绝平行趋势。', admission: '已准入', permitted: ['approve', 'reject'] as const },
  { id: 'claim-3', text: '融资约束代理值的变化与理论机制方向一致，但不单独构成因果机制识别。', admission: '限定表述', permitted: ['approve', 'reject'] as const },
  { id: 'claim-4', text: '全国碳市场已显著促进企业绿色创新。', admission: '当前数据不准入', permitted: ['reject'] as const },
]

function nowIso(): string {
  return new Date().toISOString()
}

function createShowcaseTask(): MockTask {
  const timestamp = '2026-08-30T08:00:00.000Z'
  return {
    id: SHOWCASE_TASK_ID,
    title: '碳市场约束能否转化为企业绿色创新？',
    mode: 'discovery_blind',
    status: 'completed',
    createdAt: timestamp,
    updatedAt: timestamp,
    progressAt: timestamp,
    stages: SCRIPT.map((stage) => ({
      ...stage,
      artifacts: stage.artifacts.map((artifact) => ({ ...artifact })),
      status: 'done',
      revealed: stage.lines.length,
      gateDecision: stage.gate ? 'approve' : undefined,
      gateComment: stage.gate ? '示范研究已完成该阶段的人工确认。' : undefined,
    })),
  }
}

function upgradeTasks(tasks: MockTask[]): MockTask[] {
  return [
    createShowcaseTask(),
    ...tasks.filter((task) => task.id !== SHOWCASE_TASK_ID),
  ]
}

function loadAll(): MockTask[] {
  try {
    const raw = localStorage.getItem(MOCK_TASK_STORE_KEY)
    if (!raw) {
      const tasks = [createShowcaseTask()]
      saveAll(tasks)
      return tasks
    }
    const parsed = JSON.parse(raw) as unknown
    if (Array.isArray(parsed)) {
      const tasks = upgradeTasks(parsed as MockTask[])
      saveAll(tasks)
      return tasks
    }
    if (
      parsed
      && typeof parsed === 'object'
      && Array.isArray((parsed as Partial<MockTaskStore>).tasks)
    ) {
      const store = parsed as Partial<MockTaskStore>
      const tasks = store.version === MOCK_TASK_STORE_VERSION
        ? store.tasks as MockTask[]
        : upgradeTasks(store.tasks as MockTask[])
      if (store.version !== MOCK_TASK_STORE_VERSION) saveAll(tasks)
      return tasks
    }
    const tasks = [createShowcaseTask()]
    saveAll(tasks)
    return tasks
  } catch {
    return [createShowcaseTask()]
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
