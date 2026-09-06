import type {
  CaseSubmissionInput,
  DataStructure,
  HypothesisInput,
  VariableInput,
} from '../runtime/types'
import type {
  MockGate,
  MockGateAction,
  MockMode,
  MockTask,
  MockTaskSummary,
} from '../data/mockPipeline'

export type ResourceKind = 'literature' | 'policy' | 'dataset' | 'method'

export type ProjectMode = 'discovery_blind' | 'reproduction_aligned'

export type ResourceAvailability = 'available' | 'metadata_only' | 'unavailable'

export type ResourceAttributeValue = string | string[] | number | boolean

export interface ResourceDetail {
  id: string
  kind: ResourceKind
  title: string
  summary?: string
  source: string
  tags: string[]
  availability: ResourceAvailability
  attributes: Record<string, ResourceAttributeValue>
}

export interface ResourceQuery {
  kind: ResourceKind
  search?: string
  filters?: Record<string, string | string[]>
  cursor?: string | null
  pageSize?: number
}

export interface ResourcePage {
  items: ResourceDetail[]
  total: number
  nextCursor: string | null
  hasMore: boolean
}

export type DiscoveryStep = 1 | 2 | 3 | 4 | 5 | 6

export interface DiscoveryBrief {
  researchQuestion: string
  unitOfAnalysis: string
  samplePeriod: string
  goal: string
  constraints: string[]
  dataStructureHint: DataStructure
}

export interface GapCard {
  id: string
  title: string
  evidence: string
  opportunity: string
  resourceIds: string[]
}

export interface IdeaCard {
  id: string
  title: string
  hypothesis: string
  expectedDirection: HypothesisInput['expectedDirection']
  mechanism: string
  variables: VariableInput[]
  pareto: {
    novelty: number
    feasibility: number
    identification: number
    dataReadiness: number
    policyValue: number
  }
}

export type ScientificTenItemStatus = 'evidence_bound' | 'conditional' | 'pending'

export interface ScientificTenDraftItem {
  itemNo: number
  title: string
  content: string
  status: ScientificTenItemStatus
  evidenceRefs: string[]
  unresolvedActions: string[]
  confirmed: boolean
}

export type ResearchFigureLanguage = 'zh' | 'en'

export type ScientificFigureKind = 'mechanism' | 'event_study' | 'coefficient' | 'trend'

export interface ScientificFigureCopy {
  title: string
  subtitle: string
  xLabel: string
  yLabel: string
  legend: string[]
}

export interface ScientificFigureNode {
  id: string
  role: 'predictor' | 'mechanism' | 'outcome' | 'boundary'
  labelZh: string
  labelEn: string
}

export interface ScientificFigureDraft {
  id: string
  kind: ScientificFigureKind
  role: 'research_design' | 'planned_result'
  dataStatus: 'project_bound' | 'awaiting_estimates'
  copy: Record<ResearchFigureLanguage, ScientificFigureCopy>
  sourceRefs: string[]
  nodes?: ScientificFigureNode[]
}

export interface ScientificTenDraft {
  generatedAt: string
  sourceIdeaId: string
  status: 'draft' | 'confirmed'
  confirmedAt?: string
  items: ScientificTenDraftItem[]
  figureLanguage: ResearchFigureLanguage
  figures: ScientificFigureDraft[]
}

export type ScientificTenItemPatch = Partial<Pick<
  ScientificTenDraftItem,
  'content' | 'unresolvedActions' | 'confirmed'
>>

export type ScientificFigureCopyPatch = Partial<Pick<
  ScientificFigureCopy,
  'title' | 'subtitle' | 'xLabel' | 'yLabel' | 'legend'
>>

export interface DiscoveryDraft {
  currentStep: DiscoveryStep
  completedSteps: DiscoveryStep[]
  brief: DiscoveryBrief
  gapCards: GapCard[]
  ideaCards: IdeaCard[]
  selectedIdeaId?: string
  scientificTen?: ScientificTenDraft
}

export interface ProjectResourceLink {
  projectId: string
  kind: ResourceKind
  resourceId: string
  addedAt: string
}

export interface Project {
  id: string
  title: string
  summary: string
  mode: ProjectMode
  status: 'draft' | 'active' | 'handoff_ready' | 'archived'
  createdAt: string
  updatedAt: string
  discovery: DiscoveryDraft
  resources: ProjectResourceLink[]
  taskIds: string[]
}

export interface EvidenceBundle {
  projectId: string
  links: ProjectResourceLink[]
  resources: Record<ResourceKind, ResourceDetail[]>
  counts: Record<ResourceKind, number>
}

export interface DiscoveryHandoff {
  projectId: string
  generatedAt: string
  caseInput: CaseSubmissionInput
  missingFields: string[]
  evidenceBundle: EvidenceBundle
  readyForFormalTask: boolean
}

export interface ArtifactView {
  id: string
  name: string
  kind: 'document' | 'table' | 'figure' | 'data' | 'log'
  status: 'pending' | 'ready' | 'failed'
  description: string
  createdAt?: string
}

export interface GateView {
  id: 'H1' | 'H2' | 'H3' | 'H4'
  title: string
  status: 'pending' | 'waiting' | 'approved' | 'revised' | 'rejected'
  actions: string[]
  description: string
}

export interface WorkflowStageView {
  id: string
  order: number
  title: string
  description: string
  status: 'pending' | 'running' | 'waiting_human' | 'succeeded' | 'failed' | 'blocked'
  executionStatus: string
  scientificStatus: string
  gate?: GateView
  artifacts: ArtifactView[]
}

export interface CreateProjectInput {
  title: string
  summary?: string
  mode?: ProjectMode
  brief?: Partial<DiscoveryBrief>
}

export type UpdateProjectInput = Partial<Pick<Project, 'title' | 'summary' | 'mode' | 'status' | 'taskIds'>>

export interface FrontendDataSource {
  listProjects(): Project[]
  getProject(id: string): Project | null
  createProject(input: CreateProjectInput): Project
  updateProject(id: string, patch: UpdateProjectInput): Project | null
  deleteProjects(ids: string[]): number
  getSelectedProjectId(): string | null
  setSelectedProjectId(id: string | null): void
  updateDiscoveryDraft(id: string, patch: Partial<DiscoveryDraft>): Project | null
  updateDiscoveryStep(id: string, step: DiscoveryStep, patch?: Partial<DiscoveryDraft>): Project | null
  selectDiscoveryIdea(id: string, ideaId: string | null): Project | null
  generateScientificTen(id: string): Project | null
  generateScientificFigures(id: string): Project | null
  setScientificFigureLanguage(id: string, language: ResearchFigureLanguage): Project | null
  updateScientificFigureCopy(
    id: string,
    figureId: string,
    language: ResearchFigureLanguage,
    patch: ScientificFigureCopyPatch,
  ): Project | null
  updateScientificTenItem(id: string, itemNo: number, patch: ScientificTenItemPatch): Project | null
  confirmScientificTen(id: string): Project | null
  queryResources(query: ResourceQuery): ResourcePage
  getResource(kind: ResourceKind, id: string): ResourceDetail | null
  addProjectResource(projectId: string, kind: ResourceKind, resourceId: string): ProjectResourceLink | null
  removeProjectResource(projectId: string, kind: ResourceKind, resourceId: string): boolean
  getEvidenceBundle(projectId: string): EvidenceBundle
  buildDiscoveryHandoff(projectId: string): DiscoveryHandoff | null
  listDemoTasks(): MockTaskSummary[]
  getDemoTask(id: string): MockTask | null
  isDemoTaskId(id: string): boolean
  createDemoTask(prompt: string, mode: MockMode): MockTask
  deleteDemoTask(id: string): void
  decideDemoGate(id: string, gate: MockGate, action: MockGateAction, comment?: string): MockTask | null
  subscribeDemoTask(id: string, listener: (task: MockTask) => void): () => void
  subscribeDemoTasks(listener: () => void): () => void
  subscribe(listener: () => void): () => void
}
