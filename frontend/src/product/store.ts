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
  UpdateProjectInput,
} from './types'

export const PRODUCT_STORE_VERSION = 1 as const
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

const SEED_TIMESTAMP = '2026-07-30T00:00:00.000Z'

function seedIdeaCards(): IdeaCard[] {
  return [
    {
      id: 'idea-policy-innovation',
      title: '绿色金融试验区与企业绿色创新',
      hypothesis: '绿色金融改革创新试验区政策促进企业绿色创新。',
      expectedDirection: 'positive',
      mechanism: '融资约束缓解与绿色项目激励共同提高企业绿色创新投入。',
      variables: [
        { name: 'green_patent', label: '绿色专利申请量', role: 'outcome', definition: '企业年度绿色发明专利申请数量', source: '待确认的数据来源' },
        { name: 'treat_post', label: '政策处理变量', role: 'treatment', definition: '试验区企业与政策实施后时期的交互项', source: '待人工核验的政策清单' },
        { name: 'firm_id', label: '企业代码', role: 'id', definition: '企业唯一标识', source: '待确认的数据来源' },
        { name: 'year', label: '年份', role: 'time', definition: '会计年度', source: '待确认的数据来源' },
      ],
      pareto: { novelty: 4, feasibility: 3, identification: 4, dataReadiness: 2, policyValue: 5 },
    },
    {
      id: 'idea-credit-allocation',
      title: '绿色信贷与高污染企业融资结构',
      hypothesis: '绿色信贷政策改变高污染企业的融资结构。',
      expectedDirection: 'unspecified',
      mechanism: '银行环境风险定价改变不同融资来源的相对成本。',
      variables: [],
      pareto: { novelty: 3, feasibility: 4, identification: 3, dataReadiness: 3, policyValue: 4 },
    },
  ]
}

export function createSeedProductState(): ProductState {
  const projectId = 'project-green-finance-demo'
  const resources: ProjectResourceLink[] = [
    { projectId, kind: 'literature', resourceId: 'lit-001', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'policy', resourceId: 'policy-001', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'dataset', resourceId: 'dataset-007', addedAt: SEED_TIMESTAMP },
    { projectId, kind: 'method', resourceId: 'method-002', addedAt: SEED_TIMESTAMP },
  ]
  return {
    version: PRODUCT_STORE_VERSION,
    selectedProjectId: projectId,
    projects: [{
      id: projectId,
      title: '绿色金融政策与企业创新',
      summary: '前端演示项目：从研究发现到 CaseSubmission 草稿。',
      mode: 'discovery_blind',
      status: 'active',
      createdAt: SEED_TIMESTAMP,
      updatedAt: SEED_TIMESTAMP,
      resources,
      taskIds: [],
      discovery: {
        currentStep: 3,
        completedSteps: [1, 2],
        brief: {
          researchQuestion: '绿色金融改革创新试验区政策是否促进企业绿色创新？',
          unitOfAnalysis: '企业—年度',
          samplePeriod: '2012–2023',
          goal: '评估政策效应并比较可能的作用机制。',
          constraints: ['不得使用原论文结论、回归结果或未授权材料。'],
          dataStructureHint: 'panel',
        },
        gapCards: [{
          id: 'gap-mechanism',
          title: '主动创新与被动收缩仍需区分',
          evidence: '现有目录文献更多报告总体效应，机制区分仍不充分。',
          opportunity: '比较绿色创新投入与融资结构两条可检验路径。',
          resourceIds: ['lit-001', 'lit-002'],
        }],
        ideaCards: seedIdeaCards(),
      },
    }],
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
  const projects = rawProjects
    .map(normalizeProject)
    .filter((project): project is Project => project !== null)
  const requestedSelectedId = typeof raw.selectedProjectId === 'string' ? raw.selectedProjectId : null
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

function mergeDiscovery(draft: DiscoveryDraft, patch: Partial<DiscoveryDraft>): DiscoveryDraft {
  return {
    ...draft,
    ...patch,
    completedSteps: patch.completedSteps ? [...new Set(patch.completedSteps)] : draft.completedSteps,
    brief: patch.brief ? { ...draft.brief, ...patch.brief } : draft.brief,
    gapCards: patch.gapCards ? [...patch.gapCards] : draft.gapCards,
    ideaCards: patch.ideaCards ? [...patch.ideaCards] : draft.ideaCards,
  }
}

export function updateDiscoveryDraft(id: string, patch: Partial<DiscoveryDraft>): Project | null {
  const state = readStoredState()
  const project = state.projects.find((candidate) => candidate.id === id)
  if (!project) return null
  project.discovery = mergeDiscovery(project.discovery, patch)
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
  project.discovery.selectedIdeaId = ideaId ?? undefined
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
