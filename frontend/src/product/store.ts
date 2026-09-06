import { getResource } from './catalog'
import type {
  CreateProjectInput,
  DiscoveryDraft,
  DiscoveryHandoff,
  DiscoveryStep,
  EvidenceBundle,
  IdeaCard,
  Project,
  ProjectResourceLink,
  ResourceKind,
  ResearchFigureLanguage,
  ScientificFigureCopy,
  ScientificFigureCopyPatch,
  ScientificFigureDraft,
  ScientificFigureNode,
  ScientificTenDraft,
  ScientificTenDraftItem,
  ScientificTenItemPatch,
  UpdateProjectInput,
} from './types'

export const PRODUCT_STORE_VERSION = 5 as const
export const PRODUCT_STORE_KEY = 'hypoweaver.product.v1'
export const MAX_LOCAL_PROJECTS = 50

export interface ProductState {
  version: typeof PRODUCT_STORE_VERSION
  projects: Project[]
  selectedProjectId: string | null
}

export interface ProductStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const listeners = new Set<() => void>()
const fallbackValues = new Map<string, string>()
const fallbackStorage: ProductStorage = {
  getItem: (key) => fallbackValues.get(key) ?? null,
  setItem: (key, value) => { fallbackValues.set(key, value) },
  removeItem: (key) => { fallbackValues.delete(key) },
}

let storageOverride: ProductStorage | undefined
let projectSequence = 0

function currentStorage(): ProductStorage {
  if (storageOverride) return storageOverride
  try {
    if (typeof localStorage !== 'undefined') return localStorage
  } catch {
    // Some privacy modes expose localStorage but reject access.
  }
  return fallbackStorage
}

function isoNow(): string {
  return new Date().toISOString()
}

function emptyDiscoveryDraft(): DiscoveryDraft {
  return {
    currentStep: 1,
    completedSteps: [],
    brief: {
      researchQuestion: '',
      unitOfAnalysis: '',
      samplePeriod: '',
      goal: '',
      constraints: [],
      dataStructureHint: 'unknown',
    },
    gapCards: [],
    ideaCards: [],
  }
}

const SEED_TIMESTAMP = '2026-09-05T08:00:00.000Z'
export const SHOWCASE_PROJECT_ID = 'project-carbon-market-showcase'
export const SHOWCASE_TASK_ID = 'mock-carbon-market-showcase'
const LEGACY_SEED_PROJECT_ID = 'project-green-finance-demo'

function seedIdeaCards(): IdeaCard[] {
  return [
    {
      id: 'idea-carbon-market-innovation',
      title: '碳市场约束与企业绿色技术创新',
      hypothesis: '在公开复现样本及原数据政策暴露编码下，碳政策暴露与企业高质量绿色技术创新增加相一致。',
      expectedDirection: 'positive',
      mechanism: '碳价与履约约束提高绿色研发的相对收益，融资条件变化影响企业把政策压力转化为长期创新的能力。',
      variables: [
        { name: 'green_invention', label: '绿色发明专利', role: 'outcome', definition: '企业年度绿色发明专利申请量加一取对数', source: '企业绿色专利指标目录' },
        { name: 'source_policy_post', label: '碳政策暴露', role: 'exposure', definition: '公开数据发布者提供的企业—年份政策暴露编码', source: 'Mendeley Data 公开复现面板' },
        { name: 'firm_id', label: '企业代码', role: 'id', definition: '上市公司统一企业标识', source: '上市公司财务指标目录' },
        { name: 'year', label: '年份', role: 'time', definition: '会计年度', source: '上市公司财务指标目录' },
        { name: 'abs_sa', label: '融资约束', role: 'mediator', definition: 'SA 融资约束指数绝对值', source: 'Mendeley Data 公开复现面板' },
      ],
      pareto: { novelty: 5, feasibility: 5, identification: 4, dataReadiness: 5, policyValue: 5 },
    },
    {
      id: 'idea-carbon-market-productivity',
      title: '碳市场与企业全要素生产率',
      hypothesis: '全国碳市场通过推动生产工艺升级改善纳入企业的全要素生产率。',
      expectedDirection: 'positive',
      mechanism: '碳成本倒逼要素重配与低碳工艺更新。',
      variables: [],
      pareto: { novelty: 4, feasibility: 3, identification: 4, dataReadiness: 3, policyValue: 5 },
    },
    {
      id: 'idea-carbon-disclosure-financing',
      title: '碳信息披露与债务融资成本',
      hypothesis: '更充分的碳信息披露降低高碳企业的债务融资成本。',
      expectedDirection: 'negative',
      mechanism: '披露降低环境风险信息不对称并改善债权人定价。',
      variables: [],
      pareto: { novelty: 4, feasibility: 3, identification: 3, dataReadiness: 2, policyValue: 4 },
    },
  ]
}

function showcaseScientificTen(): ScientificTenDraft {
  const titles = [
    '研究问题与项目定位', '研究空白与贡献边界', '核心假设与可证伪预测', '竞争机制与理论路径',
    '研究对象、处理与边界条件', '变量操作化与测量口径', '数据、授权与连接可行性', '识别策略与方法实现',
    '诊断、稳健性与停止规则', '阶段产物、Go/No-Go 与主张边界',
  ]
  const contents = [
    '以全国碳市场与企业高质量绿色创新为起点，经数据执行门把当前可执行问题收敛为区域碳政策公开复现，并保留全国命题作为确认性扩展。',
    '现有研究多关注碳试点的减排或专利总量效应；本研究进一步区分绿色发明与实用新型，并把融资条件、动态路径和可复算结论置于同一证据链。',
    '核心假设：碳政策暴露与绿色发明专利增加相一致；可证伪预测是处理前动态无系统差异、政策后系数为正且核心稳健性方向一致。',
    '主机制为碳价与履约约束提高绿色研发相对收益、融资条件改善支持长期研发；市场竞争作为边界条件，替代解释包括行业景气与共同年份冲击。',
    '分析单位为企业—年度，样本期为 2010—2021 年；主样本包含 1,183 家企业、14,196 条平衡面板观测，事件研究排除政策路径回退企业。',
    '主结果为 ln（1＋绿色发明专利独立申请＋联合申请）；解释变量为源定义政策暴露；控制企业规模、资产负债率与资产收益率。',
    '数据来自 Mendeley Data 的 CC BY 4.0 公开面板；源文件、21 字段最小抽取、变量映射、协议和结果均保存 SHA-256。',
    '采用企业与年份固定效应、企业聚类标准误、单调路径事件研究和 499 次完整政策轨迹置换；错位处理 TWFE 动态系数只作诊断。',
    '执行无控制、剔除 2021 年、单调路径、独立发明、全部绿色专利、实用新型对照和加入 HHI 七项稳健性；产权编码不明则停止分组。',
    '形成真实千问回执、两轮冻结协议、回归表、三张期刊图、16 项独立复算和主张台账；区域公开复现可报告，全国因果命题进入下一阶段。',
  ]
  const evidenceRefs = ['lit-007', 'policy-007', 'dataset-013', 'method-001', 'method-002']
  return {
    generatedAt: SEED_TIMESTAMP,
    sourceIdeaId: 'idea-carbon-market-innovation',
    status: 'confirmed',
    confirmedAt: SEED_TIMESTAMP,
    items: contents.map((content, index) => ({
      itemNo: index + 1,
      title: titles[index],
      content,
      status: 'evidence_bound' as const,
      evidenceRefs,
      unresolvedActions: [],
      confirmed: true,
    })),
    figureLanguage: 'zh',
    figures: [
      {
        id: 'figure-carbon-mechanism', kind: 'mechanism', role: 'research_design', dataStatus: 'project_bound',
        copy: {
          zh: { title: '碳市场促进企业绿色创新的作用机制', subtitle: '价格约束、融资条件与创新激励', xLabel: '政策暴露', yLabel: '高质量绿色创新', legend: ['主路径', '机制路径'] },
          en: { title: 'Carbon Markets and Corporate Green Innovation', subtitle: 'Policy exposure, financing and innovation', xLabel: 'Policy exposure', yLabel: 'Green innovation', legend: ['Main path', 'Mechanism'] },
        },
        sourceRefs: evidenceRefs,
        nodes: [
          { id: 'ets', role: 'predictor', labelZh: '碳政策暴露', labelEn: 'Carbon-policy exposure' },
          { id: 'price', role: 'mechanism', labelZh: '规制与价格信号', labelEn: 'Regulation and price signal' },
          { id: 'disclosure', role: 'mechanism', labelZh: '融资约束缓解', labelEn: 'Financing-constraint relief' },
          { id: 'innovation', role: 'outcome', labelZh: '高质量绿色创新', labelEn: 'High-quality green innovation' },
        ],
      },
      {
        id: 'figure-carbon-event', kind: 'event_study', role: 'planned_result', dataStatus: 'project_bound',
        copy: {
          zh: { title: '碳政策暴露的动态创新效应', subtitle: '首次暴露前后事件研究估计', xLabel: '相对首次暴露年份', yLabel: '绿色发明专利系数', legend: ['点估计', '95% 置信区间'] },
          en: { title: 'Dynamic Innovation Pattern around Carbon-Policy Exposure', subtitle: 'Event-study estimates', xLabel: 'Event time', yLabel: 'Green-invention coefficient', legend: ['Estimate', '95% CI'] },
        },
        sourceRefs: ['method-001', 'policy-007'],
      },
      {
        id: 'figure-carbon-coefficient', kind: 'coefficient', role: 'planned_result', dataStatus: 'project_bound',
        copy: {
          zh: { title: '主效应与稳健性估计', subtitle: '不同样本、口径与识别设定的系数比较', xLabel: '估计值与 95% 置信区间', yLabel: '模型设定', legend: ['绿色发明专利'] },
          en: { title: 'Main and Robustness Estimates', subtitle: 'Coefficient comparison across specifications', xLabel: 'Estimate and 95% CI', yLabel: 'Specification', legend: ['Green invention patents'] },
        },
        sourceRefs: ['method-001', 'dataset-004'],
      },
    ],
  }
}

function createShowcaseProject(): Project {
  const projectId = SHOWCASE_PROJECT_ID
  const resources: ProjectResourceLink[] = [
    { projectId, kind: 'literature', resourceId: 'lit-007', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'policy', resourceId: 'policy-007', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'dataset', resourceId: 'dataset-013', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'method', resourceId: 'method-001', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'method', resourceId: 'method-002', addedAt: SEED_TIMESTAMP },
  ]
  return {
    id: projectId,
    title: '碳市场约束能否转化为企业绿色创新？',
    summary: '从全国碳市场问题出发，经数据执行门收敛为区域碳政策公开复现；真实估计、事件研究、轨迹置换和独立复算均已完成。',
    mode: 'discovery_blind',
    status: 'handoff_ready',
    createdAt: SEED_TIMESTAMP,
    updatedAt: SEED_TIMESTAMP,
    resources,
    taskIds: [SHOWCASE_TASK_ID],
    discovery: {
      currentStep: 6,
      completedSteps: [1, 2, 3, 4, 5, 6],
      brief: {
        researchQuestion: '碳市场政策暴露能否促进企业高质量绿色技术创新，并通过融资条件变化形成持续影响？',
        unitOfAnalysis: '企业—年度',
        samplePeriod: '2010—2021',
        goal: '复现碳政策暴露与绿色发明专利的关系，检验动态趋势、融资约束机制与竞争异质性，并保留全国市场确认性扩展。',
        constraints: ['政策暴露按公开数据原字段解释，不改写为全国碳市场官方履约名单。', '若前趋势、稳健性或独立复算不通过，则降低结论强度并回到研究设计。'],
        dataStructureHint: 'panel',
      },
      gapCards: [
        { id: 'gap-national-market', title: '全国命题与当前数据范围需要分层', evidence: '公开许可面板止于2021年，不能提供全国市场启动后的充分结果期。', opportunity: '先完成区域碳政策公开复现，同时把全国市场命题编译为明确的数据补齐任务。', resourceIds: ['dataset-013', 'policy-007'] },
        { id: 'gap-quality', title: '创新数量与创新质量需要区分', evidence: '绿色专利总量可能包含策略性低质量申请，难以代表实质性技术进步。', opportunity: '以绿色发明为主结果，并用实用新型作为质量区分对照。', resourceIds: ['dataset-013'] },
        { id: 'gap-mechanism', title: '融资条件与竞争边界需要联合检验', evidence: '平均关联无法解释企业如何把政策压力转化为长期研发。', opportunity: '使用SA融资约束代理值和行业HHI，分别检验机制一致性与竞争异质性。', resourceIds: ['dataset-013', 'lit-007'] },
      ],
      ideaCards: seedIdeaCards(),
      selectedIdeaId: 'idea-carbon-market-innovation',
      scientificTen: showcaseScientificTen(),
    },
  }
}

export function createSeedProductState(): ProductState {
  const showcase = createShowcaseProject()
  return {
    version: PRODUCT_STORE_VERSION,
    selectedProjectId: showcase.id,
    projects: [showcase],
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function normalizeFigureCopy(value: unknown): ScientificFigureCopy {
  const copy = isRecord(value) ? value : {}
  return {
    title: stringValue(copy.title),
    subtitle: stringValue(copy.subtitle),
    xLabel: stringValue(copy.xLabel),
    yLabel: stringValue(copy.yLabel),
    legend: stringArray(copy.legend).slice(0, 8),
  }
}

function normalizeScientificFigure(value: unknown): ScientificFigureDraft | null {
  if (!isRecord(value) || !isRecord(value.copy)) return null
  const kind = String(value.kind)
  const role = String(value.role)
  const dataStatus = String(value.dataStatus)
  if (
    !['mechanism', 'event_study', 'coefficient', 'trend'].includes(kind)
    || !['research_design', 'planned_result'].includes(role)
    || !['project_bound', 'awaiting_estimates'].includes(dataStatus)
  ) return null
  const nodes = Array.isArray(value.nodes)
    ? value.nodes.flatMap((candidate): ScientificFigureNode[] => {
      if (!isRecord(candidate)) return []
      const nodeRole = String(candidate.role)
      if (!['predictor', 'mechanism', 'outcome', 'boundary'].includes(nodeRole)) return []
      return [{
        id: stringValue(candidate.id),
        role: nodeRole as ScientificFigureNode['role'],
        labelZh: stringValue(candidate.labelZh),
        labelEn: stringValue(candidate.labelEn),
      }]
    }).slice(0, 8)
    : undefined
  return {
    id: stringValue(value.id),
    kind: kind as ScientificFigureDraft['kind'],
    role: role as ScientificFigureDraft['role'],
    dataStatus: dataStatus as ScientificFigureDraft['dataStatus'],
    copy: {
      zh: normalizeFigureCopy(value.copy.zh),
      en: normalizeFigureCopy(value.copy.en),
    },
    sourceRefs: stringArray(value.sourceRefs),
    nodes,
  }
}

function normalizeScientificTen(value: unknown): ScientificTenDraft | undefined {
  if (!isRecord(value) || !Array.isArray(value.items)) return undefined
  const items = value.items.flatMap((candidate): ScientificTenDraftItem[] => {
    if (!isRecord(candidate)) return []
    const itemNo = Number(candidate.itemNo)
    const status = String(candidate.status)
    if (
      !Number.isInteger(itemNo)
      || itemNo < 1
      || itemNo > 10
      || !['evidence_bound', 'conditional', 'pending'].includes(status)
    ) return []
    return [{
      itemNo,
      title: stringValue(candidate.title),
      content: stringValue(candidate.content),
      status: status as ScientificTenDraftItem['status'],
      evidenceRefs: stringArray(candidate.evidenceRefs),
      unresolvedActions: stringArray(candidate.unresolvedActions),
      confirmed: candidate.confirmed === true,
    }]
  }).sort((left, right) => left.itemNo - right.itemNo)
  if (items.length !== 10 || items.some((item, index) => item.itemNo !== index + 1)) return undefined
  const confirmed = value.status === 'confirmed'
    && items.every((item) => item.confirmed && item.content.trim())
  return {
    generatedAt: stringValue(value.generatedAt, SEED_TIMESTAMP),
    sourceIdeaId: stringValue(value.sourceIdeaId),
    status: confirmed ? 'confirmed' : 'draft',
    confirmedAt: confirmed ? stringValue(value.confirmedAt, SEED_TIMESTAMP) : undefined,
    items,
    figureLanguage: value.figureLanguage === 'en' ? 'en' : 'zh',
    figures: Array.isArray(value.figures)
      ? value.figures.flatMap((candidate) => {
        const figure = normalizeScientificFigure(candidate)
        return figure ? [figure] : []
      }).slice(0, 6)
      : [],
  }
}

function normalizeDiscovery(value: unknown): DiscoveryDraft {
  const fallback = emptyDiscoveryDraft()
  if (!isRecord(value)) return fallback
  const brief = isRecord(value.brief) ? value.brief : {}
  const rawStep = Number(value.currentStep)
  const currentStep = ([1, 2, 3, 4, 5, 6] as DiscoveryStep[]).includes(rawStep as DiscoveryStep)
    ? rawStep as DiscoveryStep
    : 1
  const completedSteps = Array.isArray(value.completedSteps)
    ? value.completedSteps
      .filter((item): item is DiscoveryStep => (
        typeof item === 'number' && ([1, 2, 3, 4, 5, 6] as number[]).includes(item)
      ))
    : []
  return {
    currentStep,
    completedSteps: [...new Set(completedSteps)].sort((left, right) => left - right),
    brief: {
      researchQuestion: stringValue(brief.researchQuestion),
      unitOfAnalysis: stringValue(brief.unitOfAnalysis),
      samplePeriod: stringValue(brief.samplePeriod),
      goal: stringValue(brief.goal),
      constraints: stringArray(brief.constraints),
      dataStructureHint: (
        ['cross_section', 'panel', 'time_series', 'spatial_panel', 'event', 'unknown'] as const
      ).includes(brief.dataStructureHint as never)
        ? brief.dataStructureHint as DiscoveryDraft['brief']['dataStructureHint']
        : 'unknown',
    },
    gapCards: Array.isArray(value.gapCards) ? value.gapCards as DiscoveryDraft['gapCards'] : [],
    ideaCards: Array.isArray(value.ideaCards) ? value.ideaCards as DiscoveryDraft['ideaCards'] : [],
    selectedIdeaId: typeof value.selectedIdeaId === 'string' ? value.selectedIdeaId : undefined,
    scientificTen: normalizeScientificTen(value.scientificTen),
  }
}

function normalizeResourceLinks(projectId: string, value: unknown): ProjectResourceLink[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  return value.flatMap((candidate) => {
    if (!isRecord(candidate)) return []
    const kind = candidate.kind
    if (!['literature', 'policy', 'dataset', 'method'].includes(String(kind))) return []
    const resourceId = stringValue(candidate.resourceId)
    const key = `${kind}:${resourceId}`
    if (!resourceId || seen.has(key) || !getResource(kind as ResourceKind, resourceId)) return []
    seen.add(key)
    return [{
      projectId,
      kind: kind as ResourceKind,
      resourceId,
      addedAt: stringValue(candidate.addedAt, SEED_TIMESTAMP),
    }]
  })
}

function normalizeProject(value: unknown, index: number): Project | null {
  if (!isRecord(value)) return null
  const id = stringValue(value.id, `migrated-project-${index + 1}`)
  const title = stringValue(value.title, '未命名研究')
  const createdAt = stringValue(value.createdAt, SEED_TIMESTAMP)
  const mode = value.mode === 'reproduction_aligned' ? 'reproduction_aligned' : 'discovery_blind'
  const status = ['draft', 'active', 'handoff_ready', 'archived'].includes(String(value.status))
    ? value.status as Project['status']
    : 'draft'
  return {
    id,
    title,
    summary: stringValue(value.summary),
    mode,
    status,
    createdAt,
    updatedAt: stringValue(value.updatedAt, createdAt),
    discovery: normalizeDiscovery(value.discovery),
    resources: normalizeResourceLinks(id, value.resources),
    taskIds: stringArray(value.taskIds),
  }
}

export function migrateProductState(raw: unknown): ProductState {
  if (!isRecord(raw)) return createSeedProductState()
  const rawProjects = Array.isArray(raw.projects) ? raw.projects : []
  let projects = rawProjects
    .map(normalizeProject)
    .filter((project): project is Project => project !== null)
  let requestedSelectedId = typeof raw.selectedProjectId === 'string' ? raw.selectedProjectId : null
  if (raw.version !== PRODUCT_STORE_VERSION) {
    projects = projects.filter((project) => (
      project.id !== LEGACY_SEED_PROJECT_ID && project.id !== SHOWCASE_PROJECT_ID
    ))
    const showcase = createShowcaseProject()
    projects.unshift(showcase)
    if (!requestedSelectedId || requestedSelectedId === LEGACY_SEED_PROJECT_ID) {
      requestedSelectedId = showcase.id
    }
  }
  return {
    version: PRODUCT_STORE_VERSION,
    projects,
    selectedProjectId: projects.some((project) => project.id === requestedSelectedId)
      ? requestedSelectedId
      : projects[0]?.id ?? null,
  }
}

function cloneState(state: ProductState): ProductState {
  return JSON.parse(JSON.stringify(state)) as ProductState
}

function readStoredState(): ProductState {
  const storage = currentStorage()
  let raw: string | null = null
  try {
    raw = storage.getItem(PRODUCT_STORE_KEY)
  } catch {
    return createSeedProductState()
  }
  if (!raw) {
    const initial = createSeedProductState()
    try {
      storage.setItem(PRODUCT_STORE_KEY, JSON.stringify(initial))
    } catch {
      // The in-memory value is still usable for this read.
    }
    return initial
  }
  try {
    const parsed = JSON.parse(raw) as unknown
    const migrated = migrateProductState(parsed)
    if (!isRecord(parsed) || parsed.version !== PRODUCT_STORE_VERSION) {
      storage.setItem(PRODUCT_STORE_KEY, JSON.stringify(migrated))
    }
    return migrated
  } catch {
    const initial = createSeedProductState()
    try {
      storage.setItem(PRODUCT_STORE_KEY, JSON.stringify(initial))
    } catch {
      // Keep the recovered state in memory for this read.
    }
    return initial
  }
}

function writeState(state: ProductState): void {
  currentStorage().setItem(PRODUCT_STORE_KEY, JSON.stringify(state))
  listeners.forEach((listener) => listener())
}

export function readProductState(): ProductState {
  return cloneState(readStoredState())
}

export function subscribeProductStore(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function setProductStorageForTests(storage: ProductStorage | null): void {
  storageOverride = storage ?? undefined
  projectSequence = 0
}

export function resetProductStore(options: { seed?: boolean } = {}): void {
  const storage = currentStorage()
  storage.removeItem(PRODUCT_STORE_KEY)
  const shouldSeed = options.seed ?? true
  const nextState: ProductState = shouldSeed
    ? createSeedProductState()
    : { version: PRODUCT_STORE_VERSION, projects: [], selectedProjectId: null }
  storage.setItem(PRODUCT_STORE_KEY, JSON.stringify(nextState))
  listeners.forEach((listener) => listener())
}

export function resetProductStoreForTests(storage?: ProductStorage): void {
  if (storage) setProductStorageForTests(storage)
  resetProductStore({ seed: false })
}

export function listProjects(): Project[] {
  return readProductState().projects
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
}

export function getProject(id: string): Project | null {
  return readProductState().projects.find((project) => project.id === id) ?? null
}

export function deleteProjects(ids: string[]): number {
  const state = readStoredState()
  const requested = new Set(ids)
  const nextProjects = state.projects.filter((project) => !requested.has(project.id))
  const deletedCount = state.projects.length - nextProjects.length
  if (!deletedCount) return 0
  state.projects = nextProjects
  if (state.selectedProjectId && requested.has(state.selectedProjectId)) {
    state.selectedProjectId = nextProjects[0]?.id ?? null
  }
  writeState(state)
  return deletedCount
}

function nextProjectId(state: ProductState): string {
  let id = ''
  do {
    projectSequence += 1
    id = `project-${Date.now().toString(36)}-${projectSequence.toString(36)}`
  } while (state.projects.some((project) => project.id === id))
  return id
}

export function createProject(input: CreateProjectInput): Project {
  const state = readStoredState()
  if (state.projects.length >= MAX_LOCAL_PROJECTS) {
    throw new Error(`本地项目已达到 ${MAX_LOCAL_PROJECTS} 个上限；请先归档或导出旧项目。`)
  }
  const now = isoNow()
  const draft = emptyDiscoveryDraft()
  const project: Project = {
    id: nextProjectId(state),
    title: input.title.trim() || '未命名研究',
    summary: input.summary?.trim() ?? '',
    mode: input.mode ?? 'discovery_blind',
    status: 'draft',
    createdAt: now,
    updatedAt: now,
    resources: [],
    taskIds: [],
    discovery: {
      ...draft,
      brief: { ...draft.brief, ...input.brief },
    },
  }
  state.projects.push(project)
  state.selectedProjectId = project.id
  writeState(state)
  return cloneState({ version: PRODUCT_STORE_VERSION, projects: [project], selectedProjectId: project.id }).projects[0]
}

export function updateProject(id: string, patch: UpdateProjectInput): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === id)
  if (!project) return null
  if (patch.title !== undefined) project.title = patch.title.trim() || project.title
  if (patch.summary !== undefined) project.summary = patch.summary
  if (patch.mode !== undefined) project.mode = patch.mode
  if (patch.status !== undefined) project.status = patch.status
  if (patch.taskIds !== undefined) project.taskIds = [...patch.taskIds]
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(id)
}

export function getSelectedProjectId(): string | null {
  return readProductState().selectedProjectId
}

export function setSelectedProjectId(id: string | null): void {
  const state = readStoredState()
  state.selectedProjectId = id && state.projects.some((project) => project.id === id) ? id : null
  writeState(state)
}

function changesScientificTenInputs(patch: Partial<DiscoveryDraft>): boolean {
  return (
    patch.brief !== undefined
    || patch.gapCards !== undefined
    || patch.ideaCards !== undefined
    || patch.selectedIdeaId !== undefined
  )
}

function resetScientificTenProgress(project: Project): void {
  project.discovery.scientificTen = undefined
  project.discovery.completedSteps = project.discovery.completedSteps.filter((step) => step !== 6)
  if (project.status === 'handoff_ready' && project.taskIds.length === 0) {
    project.status = 'active'
  }
}

function mergeDiscovery(draft: DiscoveryDraft, patch: Partial<DiscoveryDraft>): DiscoveryDraft {
  const changesProposalInputs = changesScientificTenInputs(patch)
  const scientificTen = Object.prototype.hasOwnProperty.call(patch, 'scientificTen')
    ? patch.scientificTen
    : changesProposalInputs
      ? undefined
      : draft.scientificTen
  return {
    ...draft,
    ...patch,
    completedSteps: patch.completedSteps ? [...new Set(patch.completedSteps)] : draft.completedSteps,
    brief: patch.brief ? { ...draft.brief, ...patch.brief } : draft.brief,
    gapCards: patch.gapCards ? [...patch.gapCards] : draft.gapCards,
    ideaCards: patch.ideaCards ? [...patch.ideaCards] : draft.ideaCards,
    scientificTen,
  }
}

export function updateDiscoveryDraft(id: string, patch: Partial<DiscoveryDraft>): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === id)
  if (!project) return null
  project.discovery = mergeDiscovery(project.discovery, patch)
  if (changesScientificTenInputs(patch) && !Object.prototype.hasOwnProperty.call(patch, 'scientificTen')) {
    resetScientificTenProgress(project)
  }
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(id)
}

export function updateDiscoveryStep(
  id: string,
  step: DiscoveryStep,
  patch: Partial<DiscoveryDraft> = {},
): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === id)
  if (!project) return null
  const completedSteps = new Set(project.discovery.completedSteps)
  for (let previous = 1; previous < step; previous += 1) completedSteps.add(previous as DiscoveryStep)
  project.discovery = mergeDiscovery(project.discovery, {
    ...patch,
    currentStep: step,
    completedSteps: [...completedSteps].sort((left, right) => left - right),
  })
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(id)
}

export function selectDiscoveryIdea(id: string, ideaId: string | null): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === id)
  if (!project) return null
  if (ideaId && !project.discovery.ideaCards.some((idea) => idea.id === ideaId)) return null
  const preservesPreparedProposal = Boolean(
    ideaId && project.discovery.scientificTen?.sourceIdeaId === ideaId,
  )
  project.discovery.selectedIdeaId = ideaId ?? undefined
  if (!preservesPreparedProposal) resetScientificTenProgress(project)
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(id)
}

export function addProjectResource(
  projectId: string,
  kind: ResourceKind,
  resourceId: string,
): ProjectResourceLink | null {
  if (!getResource(kind, resourceId)) return null
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  if (!project) return null
  const existing = project.resources.find((link) => link.kind === kind && link.resourceId === resourceId)
  if (existing) return { ...existing }
  const link: ProjectResourceLink = { projectId, kind, resourceId, addedAt: isoNow() }
  project.resources.push(link)
  resetScientificTenProgress(project)
  project.updatedAt = link.addedAt
  writeState(state)
  return { ...link }
}

export function removeProjectResource(
  projectId: string,
  kind: ResourceKind,
  resourceId: string,
): boolean {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  if (!project) return false
  const nextResources = project.resources.filter((link) => (
    link.kind !== kind || link.resourceId !== resourceId
  ))
  if (nextResources.length === project.resources.length) return false
  project.resources = nextResources
  resetScientificTenProgress(project)
  project.updatedAt = isoNow()
  writeState(state)
  return true
}

const RESOURCE_KINDS: ResourceKind[] = ['literature', 'policy', 'dataset', 'method']

export function getEvidenceBundle(projectId: string): EvidenceBundle {
  const links = getProject(projectId)?.resources ?? []
  const resources = {
    literature: [],
    policy: [],
    dataset: [],
    method: [],
  } as EvidenceBundle['resources']
  for (const link of links) {
    const resource = getResource(link.kind, link.resourceId)
    if (resource) resources[link.kind].push(resource)
  }
  return {
    projectId,
    links,
    resources,
    counts: Object.fromEntries(
      RESOURCE_KINDS.map((kind) => [kind, resources[kind].length]),
    ) as EvidenceBundle['counts'],
  }
}

function validVariables(idea: IdeaCard | undefined): IdeaCard['variables'] {
  if (!idea) return []
  return idea.variables
    .filter((variable) => (
      variable.name.trim()
      && variable.label.trim()
      && variable.definition.trim()
      && variable.source.trim()
    ))
    .map((variable) => ({ ...variable }))
}

export function buildDiscoveryHandoff(projectId: string): DiscoveryHandoff | null {
  const project = getProject(projectId)
  if (!project) return null
  const { brief } = project.discovery
  const selectedIdea = project.discovery.ideaCards.find((idea) => (
    idea.id === project.discovery.selectedIdeaId
  ))
  const variables = validVariables(selectedIdea)
  const caseInput: DiscoveryHandoff['caseInput'] = {
    caseId: project.id,
    title: project.title.trim(),
    researchQuestion: brief.researchQuestion.trim(),
    hypotheses: selectedIdea?.hypothesis.trim()
      ? [{
        hypothesisId: selectedIdea.id,
        statement: selectedIdea.hypothesis.trim(),
        expectedDirection: selectedIdea.expectedDirection,
        mechanism: selectedIdea.mechanism.trim(),
      }]
      : [],
    unitOfAnalysis: brief.unitOfAnalysis.trim(),
    samplePeriod: brief.samplePeriod.trim(),
    dataStructureHint: brief.dataStructureHint,
    variables,
    datasetRefs: [],
    knownPolicyFacts: [],
    constraints: brief.constraints.map((item) => item.trim()).filter(Boolean),
  }
  const missingFields: string[] = []
  if (!caseInput.title) missingFields.push('title')
  if (!caseInput.researchQuestion) missingFields.push('researchQuestion')
  if (!caseInput.hypotheses.length) missingFields.push('hypotheses')
  if (!caseInput.unitOfAnalysis) missingFields.push('unitOfAnalysis')
  if (!caseInput.samplePeriod) missingFields.push('samplePeriod')
  if (!caseInput.variables.some((variable) => variable.role === 'outcome')) missingFields.push('variables.outcome')
  if (caseInput.dataStructureHint === 'panel') {
    if (!caseInput.variables.some((variable) => variable.role === 'id')) missingFields.push('variables.id')
    if (!caseInput.variables.some((variable) => variable.role === 'time')) missingFields.push('variables.time')
  }
  if (!caseInput.datasetRefs.length) missingFields.push('datasetRefs')
  if (!caseInput.knownPolicyFacts.length) missingFields.push('knownPolicyFacts (requires human confirmation)')
  return {
    projectId,
    generatedAt: isoNow(),
    caseInput,
    missingFields,
    evidenceBundle: getEvidenceBundle(projectId),
    readyForFormalTask: missingFields.length === 0,
  }
}

const SCIENTIFIC_TEN_TITLES = [
  '研究问题与项目定位',
  '研究空白与贡献边界',
  '核心假设与可证伪预测',
  '竞争机制与理论路径',
  '研究对象、处理与边界条件',
  '变量操作化与测量口径',
  '数据、授权与连接可行性',
  '识别策略与方法实现',
  '诊断、稳健性与停止规则',
  '阶段产物、Go/No-Go 与主张边界',
] as const

function uniqueStrings(values: Array<string | undefined>): string[] {
  return [...new Set(values.map((value) => value?.trim() ?? '').filter(Boolean))]
}

function scientificItem(
  itemNo: number,
  content: string,
  status: ScientificTenDraftItem['status'],
  evidenceRefs: Array<string | undefined> = [],
  unresolvedActions: Array<string | undefined> = [],
): ScientificTenDraftItem {
  return {
    itemNo,
    title: SCIENTIFIC_TEN_TITLES[itemNo - 1],
    content: content.trim(),
    status,
    evidenceRefs: uniqueStrings(evidenceRefs),
    unresolvedActions: uniqueStrings(unresolvedActions),
    confirmed: false,
  }
}

function directionLabel(direction: IdeaCard['expectedDirection']): string {
  return {
    positive: '正向',
    negative: '负向',
    nonlinear: '非线性',
    heterogeneous: '异质性',
    unspecified: '方向待确认',
  }[direction]
}

function clause(value: string): string {
  return value.trim().replace(/[。！？!?；;，,：:]+$/u, '')
}

function englishVariableLabel(name: string): string {
  return name
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .trim()
}

function buildScientificFigures(project: Project, idea: IdeaCard): ScientificFigureDraft[] {
  const variables = idea.variables
  const predictor = variables.find((variable) => (
    ['treatment', 'exposure'].includes(variable.role)
  ))
  const outcome = variables.find((variable) => variable.role === 'outcome')
  const mediator = variables.find((variable) => variable.role === 'mediator')
  const boundary = variables.find((variable) => variable.role === 'moderator')
  const node = (
    id: string,
    role: ScientificFigureNode['role'],
    variable: typeof predictor,
    fallbackZh: string,
    fallbackEn: string,
  ): ScientificFigureNode => ({
    id,
    role,
    labelZh: variable?.label?.trim() || fallbackZh,
    labelEn: variable?.name ? englishVariableLabel(variable.name) : fallbackEn,
  })
  const nodes: ScientificFigureNode[] = [
    node('predictor', 'predictor', predictor, '政策或核心解释变量', 'Treatment or exposure'),
    node('mechanism', 'mechanism', mediator, clause(idea.mechanism) || '待检验作用机制', 'Proposed mechanism'),
    node('outcome', 'outcome', outcome, '核心结果变量', 'Primary outcome'),
  ]
  if (boundary) nodes.push(node('boundary', 'boundary', boundary, '边界条件', 'Boundary condition'))
  const sourceRefs = uniqueStrings([idea.id, ...variables.map((variable) => variable.name)])
  const figures: ScientificFigureDraft[] = [{
    id: 'research-mechanism',
    kind: 'mechanism',
    role: 'research_design',
    dataStatus: 'project_bound',
    copy: {
      zh: {
        title: `${idea.title}：研究机制与可证伪路径`,
        subtitle: '研究设计图；箭头表示待检验关系，不代表实证结果',
        xLabel: '',
        yLabel: '',
        legend: ['核心解释路径', '待检验机制'],
      },
      en: {
        title: 'Research mechanism and falsifiable pathway',
        subtitle: 'Research design; arrows denote hypotheses, not empirical results',
        xLabel: '',
        yLabel: '',
        legend: ['Core explanatory path', 'Proposed mechanism'],
      },
    },
    sourceRefs,
    nodes,
  }, {
    id: 'coefficient-plan',
    kind: 'coefficient',
    role: 'planned_result',
    dataStatus: 'awaiting_estimates',
    copy: {
      zh: {
        title: '主要效应、机制与异质性估计',
        subtitle: '系数与置信区间；正式图须接入真实模型输出',
        xLabel: '估计值（95% 置信区间）',
        yLabel: '模型规格',
        legend: ['点估计', '95% 置信区间'],
      },
      en: {
        title: 'Main, mechanism, and heterogeneous effects',
        subtitle: 'Coefficients and confidence intervals; connect verified estimates for publication',
        xLabel: 'Estimate (95% CI)',
        yLabel: 'Model specification',
        legend: ['Point estimate', '95% confidence interval'],
      },
    },
    sourceRefs,
  }]
  const structure = project.discovery.brief.dataStructureHint
  const hasTime = variables.some((variable) => ['time', 'event_date'].includes(variable.role))
  if (['panel', 'spatial_panel', 'event'].includes(structure) || hasTime) {
    figures.push({
      id: 'event-study-plan',
      kind: 'event_study',
      role: 'planned_result',
      dataStatus: 'awaiting_estimates',
      copy: {
        zh: {
          title: '事件发生前后的动态效应',
          subtitle: '平行趋势与动态响应；正式图须接入真实估计及置信区间',
          xLabel: '相对事件时间',
          yLabel: '估计效应',
          legend: ['点估计', '95% 置信区间'],
        },
        en: {
          title: 'Dynamic effects around the event',
          subtitle: 'Pre-trends and dynamic responses; connect verified estimates and confidence intervals',
          xLabel: 'Time relative to event',
          yLabel: 'Estimated effect',
          legend: ['Point estimate', '95% confidence interval'],
        },
      },
      sourceRefs,
    })
  }
  if (['panel', 'spatial_panel', 'time_series'].includes(structure) || hasTime) {
    figures.push({
      id: 'trend-plan',
      kind: 'trend',
      role: 'planned_result',
      dataStatus: 'awaiting_estimates',
      copy: {
        zh: {
          title: '处理组与比较组结果趋势',
          subtitle: '描述性趋势；不得替代正式识别与推断',
          xLabel: '时间',
          yLabel: outcome?.label?.trim() || '结果变量',
          legend: ['处理组', '比较组'],
        },
        en: {
          title: 'Outcome trends for treated and comparison groups',
          subtitle: 'Descriptive trends; not a substitute for identification and inference',
          xLabel: 'Time',
          yLabel: outcome?.name ? englishVariableLabel(outcome.name) : 'Outcome',
          legend: ['Treated group', 'Comparison group'],
        },
      },
      sourceRefs,
    })
  }
  return figures
}

/** 普通项目的科学十项只绑定当前项目证据，不借用未上传的文件或未确认事实。 */
export function generateScientificTen(projectId: string): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  if (!project) return null
  const idea = project.discovery.ideaCards.find((candidate) => (
    candidate.id === project.discovery.selectedIdeaId
  ))
  if (!idea) return null
  const gap = project.discovery.gapCards[0]
  const bundle = getEvidenceBundle(projectId)
  const handoff = buildDiscoveryHandoff(projectId)
  if (!handoff) return null
  const { brief } = project.discovery
  const variables = idea.variables.map((variable) => (
    `${variable.label}（${variable.role}）：${variable.definition}；来源：${variable.source}`
  ))
  const datasetResources = bundle.resources.dataset
  const methodResources = bundle.resources.method
  const evidenceRefs = bundle.links.map((link) => `${link.kind}:${link.resourceId}`)
  const falsification = idea.expectedDirection === 'unspecified'
    ? '需在 H2 前明确方向、效应量或异质性模式；未形成可判定预测时不得宣称假设获支持。'
    : `若预先冻结的主要估计不呈${directionLabel(idea.expectedDirection)}关系，或关键诊断与稳健性检查失败，则不支持该假设。`
  const datasetSummary = datasetResources.length
    ? datasetResources.map((resource) => `${resource.title}（${resource.availability}）`).join('；')
    : '项目资源篮尚无数据资源。'
  const methodSummary = methodResources.length
    ? methodResources.map((resource) => resource.title).join('；')
    : '尚未选择方法资源。'
  const missingFields = handoff.missingFields.join('、') || '当前未发现结构化输入缺失项'
  const now = isoNow()
  project.discovery.scientificTen = {
    generatedAt: now,
    sourceIdeaId: idea.id,
    status: 'draft',
    figureLanguage: 'zh',
    figures: buildScientificFigures(project, idea),
    items: [
      scientificItem(
        1,
        `研究问题：${brief.researchQuestion || '待补充'} 项目目标：${brief.goal || '待补充'} 分析对象：${brief.unitOfAnalysis || '待补充'}；样本期间：${brief.samplePeriod || '待补充'}。`,
        brief.researchQuestion ? 'evidence_bound' : 'pending',
        [idea.id],
        brief.goal ? [] : ['补充项目目标与预期产物。'],
      ),
      scientificItem(
        2,
        gap
          ? `研究空白：${gap.title}。现有证据：${gap.evidence} 研究机会：${gap.opportunity} 贡献边界仅限当前项目资源篮，不主张领域级首次。`
          : '尚未形成可绑定证据的 GapCard；贡献边界暂不能授权。',
        gap ? 'evidence_bound' : 'pending',
        [gap?.id, ...(gap?.resourceIds ?? [])],
        gap ? [] : ['先形成并审阅 GapCard。'],
      ),
      scientificItem(
        3,
        `核心假设：${idea.hypothesis || '待补充'} 预期方向：${directionLabel(idea.expectedDirection)}。可证伪标准：${falsification}`,
        idea.hypothesis ? 'evidence_bound' : 'pending',
        [idea.id],
      ),
      scientificItem(
        4,
        `主要机制：${clause(idea.mechanism || '待补充')}。竞争机制与替代解释需在 H2 前列明，并保持与主要机制可区分。`,
        idea.mechanism ? 'evidence_bound' : 'pending',
        [idea.id, gap?.id],
        ['补充至少一条竞争机制或替代解释。'],
      ),
      scientificItem(
        5,
        `分析对象：${brief.unitOfAnalysis || '待补充'}；样本期间：${brief.samplePeriod || '待补充'}；研究约束：${clause(brief.constraints.join('；') || '待补充')}。处理定义与纳入排除规则需在 H1/H2 确认。`,
        brief.unitOfAnalysis && brief.samplePeriod ? 'conditional' : 'pending',
        [idea.id],
        handoff.missingFields.filter((field) => ['unitOfAnalysis', 'samplePeriod'].includes(field)),
      ),
      scientificItem(
        6,
        variables.length ? variables.join('\n') : '尚未提供可执行的变量定义与测量来源。',
        variables.length ? 'conditional' : 'pending',
        [idea.id],
        handoff.missingFields.filter((field) => field.startsWith('variables.')),
      ),
      scientificItem(
        7,
        `${datasetSummary} 资源篮记录只提供目录与可用性线索，不等于已绑定执行文件；正式数据仍需完成授权、文件哈希、覆盖范围和连接键审计。`,
        handoff.caseInput.datasetRefs.length ? 'conditional' : 'pending',
        datasetResources.map((resource) => `dataset:${resource.id}`),
        handoff.caseInput.datasetRefs.length
          ? []
          : ['绑定真实数据文件及其 SHA-256、大小、授权与连接键。'],
      ),
      scientificItem(
        8,
        `数据结构：${brief.dataStructureHint}。候选方法：${methodSummary} 方法只能在数据结构、识别假设和执行器均通过审计后冻结。`,
        methodResources.length ? 'conditional' : 'pending',
        methodResources.map((resource) => `method:${resource.id}`),
        methodResources.length ? ['在 H2 比较候选方法并冻结主规格。'] : ['补充候选方法与可用执行器。'],
      ),
      scientificItem(
        9,
        '诊断至少覆盖识别假设、样本支持、缺失与异常、安慰剂或伪检验、替代口径和敏感性分析。任一关键诊断失败时，停止或降级因果与机制主张。',
        'conditional',
        methodResources.map((resource) => `method:${resource.id}`),
        ['在 H2 为每项诊断填写阈值、失败动作与停止规则。'],
      ),
      scientificItem(
        10,
        `当前可产出证据篮、GapCard、HypothesisCard 与科学十项草案。正式输入缺失：${missingFields}。只有数据、方法、复现与 H3 主张授权闭合后，才允许形成实证效应或因果结论。`,
        handoff.readyForFormalTask ? 'conditional' : 'pending',
        [idea.id, gap?.id, ...evidenceRefs],
        handoff.missingFields,
      ),
    ],
  }
  project.discovery.completedSteps = project.discovery.completedSteps.filter((step) => step !== 6)
  if (project.status === 'handoff_ready' && project.taskIds.length === 0) project.status = 'active'
  project.updatedAt = now
  writeState(state)
  return getProject(projectId)
}

/** 为旧项目补齐绘图方案，不改变科学十项确认状态。 */
export function generateScientificFigures(projectId: string): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  const proposal = project?.discovery.scientificTen
  const idea = project?.discovery.ideaCards.find((candidate) => candidate.id === proposal?.sourceIdeaId)
  if (!project || !proposal || !idea) return null
  proposal.figures = buildScientificFigures(project, idea)
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(projectId)
}

export function setScientificFigureLanguage(
  projectId: string,
  language: ResearchFigureLanguage,
): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  const proposal = project?.discovery.scientificTen
  if (!project || !proposal) return null
  proposal.figureLanguage = language
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(projectId)
}

export function updateScientificFigureCopy(
  projectId: string,
  figureId: string,
  language: ResearchFigureLanguage,
  patch: ScientificFigureCopyPatch,
): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  const proposal = project?.discovery.scientificTen
  const figure = proposal?.figures.find((candidate) => candidate.id === figureId)
  if (!project || !proposal || !figure) return null
  const copy = figure.copy[language]
  if (patch.title !== undefined) copy.title = patch.title
  if (patch.subtitle !== undefined) copy.subtitle = patch.subtitle
  if (patch.xLabel !== undefined) copy.xLabel = patch.xLabel
  if (patch.yLabel !== undefined) copy.yLabel = patch.yLabel
  if (patch.legend !== undefined) copy.legend = uniqueStrings(patch.legend).slice(0, 8)
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(projectId)
}

export function updateScientificTenItem(
  projectId: string,
  itemNo: number,
  patch: ScientificTenItemPatch,
): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  const proposal = project?.discovery.scientificTen
  const item = proposal?.items.find((candidate) => candidate.itemNo === itemNo)
  if (!project || !proposal || !item) return null
  if (patch.content !== undefined) item.content = patch.content
  if (patch.unresolvedActions !== undefined) {
    item.unresolvedActions = uniqueStrings(patch.unresolvedActions)
  }
  if (patch.confirmed !== undefined) {
    item.confirmed = patch.confirmed && Boolean(item.content.trim())
  } else if (patch.content !== undefined || patch.unresolvedActions !== undefined) {
    item.confirmed = false
  }
  proposal.status = 'draft'
  proposal.confirmedAt = undefined
  project.discovery.completedSteps = project.discovery.completedSteps.filter((step) => step !== 6)
  if (project.status === 'handoff_ready' && project.taskIds.length === 0) project.status = 'active'
  project.updatedAt = isoNow()
  writeState(state)
  return getProject(projectId)
}

export function confirmScientificTen(projectId: string): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === projectId)
  const proposal = project?.discovery.scientificTen
  if (
    !project
    || !proposal
    || proposal.items.length !== 10
    || proposal.items.some((item) => !item.confirmed || !item.content.trim())
  ) return null
  const now = isoNow()
  proposal.status = 'confirmed'
  proposal.confirmedAt = now
  project.discovery.completedSteps = [...new Set([
    ...project.discovery.completedSteps,
    1, 2, 3, 4, 5, 6,
  ] as DiscoveryStep[])].sort((left, right) => left - right)
  project.updatedAt = now
  writeState(state)
  return getProject(projectId)
}
