export type NodeKind =
  | 'start'
  | 'document'
  | 'llm'
  | 'code'
  | 'gate'
  | 'router'
  | 'merge'
  | 'http'
  | 'end'
  | 'other'

export type RunStatus =
  | 'created'
  | 'running'
  | 'waiting_human'
  | 'blocked'
  | 'failed'
  | 'completed'
  | 'stopped'
  | 'cancelled'

export type StepStatus =
  | 'pending'
  | 'running'
  | 'waiting_human'
  | 'succeeded'
  | 'failed'
  | 'blocked'
  | 'skipped'

export type GateAction =
  | 'approve'
  | 'revise'
  | 'reject'
  | 'generate_plan_only'
  | 'generate_identification_failure_report'
export type ClaimDecision = 'approve' | 'downgrade' | 'reject' | 'hold'

export interface PromptContent {
  id: string
  role: string
  template: string
  rendered?: string
}

export interface WorkflowStage {
  id: string
  order: number
  title: string
  description: string
  nodeIds: string[]
}

export interface WorkflowNode {
  id: string
  title: string
  type: string
  kind: NodeKind
  stageId: string
  description: string
  position: { x: number; y: number }
  prompts: PromptContent[]
  inputSchema: unknown
  outputSchema: unknown
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
  label?: string
}

export interface WorkflowDefinition {
  id: string
  version: string
  name: string
  description: string
  stages: WorkflowStage[]
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  gates: Record<string, { state: string; decisions: string[] }>
}

export interface StepAttempt {
  id: string
  nodeId: string
  attempt: number
  status: StepStatus
  startedAt?: string
  endedAt?: string
  prompts: PromptContent[]
  input: unknown
  output: unknown
  logs: string[]
  error?: string
}

export interface RunEvent {
  seq: number
  type: string
  message: string
  timestamp: string
  nodeId?: string
  stepStatus?: StepStatus
}

export interface ClaimRecord {
  id: string
  text: string
  finalText?: string
  claimType?: string
  allowedStrength?: string
  maxAllowedStrength?: string
  admissionStatus?: 'unassessed' | 'admitted' | 'downgrade_required' | 'prohibited' | 'rejected'
  evidenceStatus?: string
  robustnessStatus?: string
  requiredCheckIds: string[]
  gateReasons: string[]
  supportingRuns: string[]
  decision?: ClaimDecision
}

export interface ManuscriptSectionView {
  id: string
  title: string
  content: string
  status: 'generated' | 'not_generated'
  claimIds: string[]
  runIds: string[]
  figureIds: string[]
  statements: ManuscriptStatementSourceView[]
}

export interface ManuscriptStatementSourceView {
  id: string
  kind: 'authorized_claim' | 'estimate_fact' | 'sample_fact' | 'diagnostic_fact' | 'citation'
  claimIds: string[]
  executionIds: string[]
  sources: Array<{
    kind: 'claim' | 'execution' | 'passage'
    id: string
    path: string
  }>
}

export interface ManuscriptPackageView {
  version: number
  irVersion: number
  mode: 'research_plan_only' | 'full_manuscript' | 'identification_failure_report'
  status: 'draft' | 'needs_revision' | 'ready_for_human_review' | 'not_generated'
  researchPlan: string
  sections: ManuscriptSectionView[]
  figureIds: string[]
  disclosures: string[]
  unresolvedIssues: string[]
  auditResult: 'not_run' | 'pass_with_no_critical_issues' | 'revise'
}

export interface FigureFileView {
  format: 'svg' | 'png' | 'pdf' | 'csv'
  mimeType: string
  sha256: string
}

export interface FigureView {
  id: string
  recipeId: string
  recipeVersion: string
  title: string
  caption: string
  altText: string
  executionIds: string[]
  claimIds: string[]
  files: FigureFileView[]
  warnings: string[]
}

export interface FigureBundleView {
  stage: 'evidence' | 'publication'
  status: 'succeeded' | 'not_generated' | 'failed'
  figures: FigureView[]
  warnings: string[]
}

export interface DesignCandidateView {
  id: string
  strategy: 'direct_baseline' | 'identification_first' | 'measurement_robustness'
  rationale: string
  methodFamily: string
  estimator: string
  formula?: string
  probeVerdict: 'pass' | 'warn' | 'fail'
  executorReady: boolean
  probeChecks: Array<{ id: string; status: 'pass' | 'warn' | 'fail'; evidence: string }>
  reviewIssueCount: number
  reviewerRejected: boolean
}

export interface DesignArenaView {
  id: string
  candidates: DesignCandidateView[]
  recommendedCandidateIds: string[]
  provisionalCandidateId?: string
  selectionRationale: string[]
}

export type ModelCallGroup = 'h1_h2' | 'h3' | 'h4'

export interface ModelUsageView {
  maxCalls: number
  llmCalls: number
  logicalCalls: number
  providerAttempts: number
  requiredLogicalCalls: number
  retryPolicy?: string
  retryMode?: string
  sharedRetrySlots: number
  sharedRetryRemaining: number
  groupUsage: Record<ModelCallGroup, number>
}

export interface Group2FeasibilityView {
  packageId: string
  handoffStatus: 'accepted_for_group2_design' | 'rejected'
  executionStatus: 'ready' | 'not_ready'
  goNoGoDecision: 'conditional_go_for_design' | 'go_for_execution' | 'no_go_return_to_group1'
  decisionRationale: string
  returnToGroup1Required: boolean
  dataMatrix: Array<{
    itemId: string
    constructName: string
    role: string
    candidateSourceIds: string[]
    sourceAccess: string
    executableAssetSupplied: boolean
    readiness: string
    nextAction: string
  }>
  methodMatrix: Array<{
    methodId: string
    name: string
    purpose: string
    implementationStatus: string
    nextAction: string
  }>
  scientificTen: Array<{
    itemNo: number
    title: string
    content: string
    status: 'evidence_bound' | 'conditional' | 'pending'
    evidenceRefs: string[]
    unresolvedActions: string[]
  }>
}

export interface Group1VerifiedBundleStatus {
  status: 'ready' | 'unavailable' | 'invalid'
  message: string
  bundleId?: string
  label?: string
  handoffId?: string
  handoffManifestSha256?: string
  verifiedArtifactCount: number
  datasetFilename?: string
  datasetSha256?: string
  datasetSizeBytes?: number
  panelRows?: number
  panelColumns?: number
  sourceConfigSha256?: string
  acceptanceRunId?: string
  acceptanceSealSha256?: string
  verifiedAt?: string
  executionStatus?: string
  scientificStatus?: string
  reproductionStatus?: string
  reproductionScope?: string
  modelProvider: 'code_owned'
  executionMode: 'external'
}

export interface ReproductionAuditView {
  status: string
  independenceScope?: string
  primaryImplementationId?: string
  replicationImplementationId?: string
  replicationRunId?: string
  differences: string[]
}

export interface SealedOutputView {
  sealAlgorithm?: string
  sealSha256?: string
}

export interface RunSnapshot {
  id: string
  version: number
  definitionId: string
  definitionVersion: string
  caseId: string
  caseName: string
  mode: 'fixture' | 'research'
  status: RunStatus
  currentNodeId?: string
  currentGate?: 'H1' | 'H2' | 'H3' | 'H4'
  lastError?: string
  modelProvider: string
  executionMode: string
  executionStatus: string
  scientificStatus: string
  planOnly: boolean
  createdAt: string
  updatedAt: string
  caseSubmission?: CaseSubmissionInput
  steps: StepAttempt[]
  events: RunEvent[]
  claims: ClaimRecord[]
  figureBundles: FigureBundleView[]
  manuscript?: ManuscriptPackageView
  designArena?: DesignArenaView
  modelUsage?: ModelUsageView
  reproductionAudit?: ReproductionAuditView
  sealedOutput?: SealedOutputView
  upstreamPackage?: {
    sourceSystem: string
    bridgeVersion: string
    packageId: string
    status: string
    manifestSha256: string
    verifiedArtifactCount: number
    evidenceRefCount?: number
    hypothesisId?: string
    gapId?: string
    corpusBoundary?: string
  }
  intakeReadiness?: {
    status: 'ready' | 'conditional' | 'blocked'
    canApproveH1: boolean
    canExecute: boolean
    blockers: string[]
    warnings: string[]
    requiredInputs: string[]
    methodRequirements: string[]
  }
  group2Feasibility?: Group2FeasibilityView
  allowedActions: string[]
}

export interface RunSummary {
  id: string
  caseName: string
  mode: 'fixture' | 'research'
  status: RunStatus
  currentGate?: 'H1' | 'H2' | 'H3' | 'H4'
  updatedAt: string
}

export type DataStructure =
  | 'cross_section'
  | 'panel'
  | 'time_series'
  | 'spatial_panel'
  | 'event'
  | 'unknown'

export type VariableRole =
  | 'outcome'
  | 'treatment'
  | 'exposure'
  | 'mediator'
  | 'moderator'
  | 'control'
  | 'id'
  | 'time'
  | 'spatial_id'
  | 'event_date'
  | 'fixed_effect'
  | 'cluster'
  | 'unknown'

export interface HypothesisInput {
  hypothesisId: string
  statement: string
  expectedDirection: 'positive' | 'negative' | 'nonlinear' | 'heterogeneous' | 'unspecified'
  mechanism: string
}

export interface VariableInput {
  name: string
  label: string
  role: VariableRole
  definition: string
  source: string
}

export interface DatasetReferenceInput {
  datasetId: string
  role: 'main' | 'supplementary'
  filename: string
  mimeType: string
  sha256: string
  sizeBytes: number
}

export interface CaseSubmissionInput {
  caseId: string
  title: string
  researchQuestion: string
  hypotheses: HypothesisInput[]
  unitOfAnalysis: string
  samplePeriod: string
  dataStructureHint: DataStructure
  variables: VariableInput[]
  datasetRefs: DatasetReferenceInput[]
  designEnvelope?: {
    benchmarkTrack: 'strict_blind' | 'reproduction_aligned'
    researchGoal: 'causal' | 'associational' | 'mechanism' | 'prediction' | 'measurement' | 'structural' | 'mixed'
    targetEstimands: string[]
    designConstraints: string[]
    requiredDiagnostics: string[]
    allowedClaimStrength: 'causal' | 'associational' | 'descriptive' | 'not_prespecified'
  }
  policyDesign?: {
    policyDate: string
    groupField: string
    timeField: string
    policyStartWeight?: number
    postStartWeight: number
    exposureName: string
    fixedEffects: string[]
    clusterFields: string[]
    clusterComposition: 'interaction'
    eventReferenceYear?: number
    eventYears: number[]
    eventRemotePreYears: number[]
    eventTermScaling: 'binary_group_year_contrast'
    placeboStartYear?: number
    placeboRepetitions?: number
    permutationScheme: 'assignment_unit_label' | 'rowwise_exposure'
    permutationUnitField?: string
    randomSeed?: number
  }
  knownPolicyFacts: string[]
  constraints: string[]
}

export interface CaseImportReport {
  datasetFilename: string
  rowCount: number
  columnCount: number
  samplePeriod?: string
  hiddenFileCount: number
  excludedFileCount: number
  reviewItems: string[]
}

export interface LocalCaseImportResult {
  case: CaseSubmissionInput
  report: CaseImportReport
}

export interface CreateRunInput {
  mode: 'fixture' | 'research'
  presetId?: string
  case?: CaseSubmissionInput
}

export interface GateDecisionInput {
  action: GateAction
  comment?: string
  claims?: Array<{ claimId: string; decision: ClaimDecision; finalText?: string; reason?: string }>
  selectedCandidateId?: string
}

export type ConfigSource = 'environment' | 'file' | 'default' | 'missing'

export interface RuntimeConfigStatus {
  configPath: string
  environmentPrecedence: boolean
  workflowApiTokenRequired: boolean
  qwenApiKey: { configured: boolean; source: ConfigSource }
  qwenModel: { value: string | null; source: ConfigSource }
  qwenBaseUrl: { value: string | null; source: ConfigSource }
  researchEngineUrl: { value: string | null; source: ConfigSource }
  researchEngineToken: { configured: boolean; source: ConfigSource }
}

export interface RuntimeConfigUpdate {
  qwenApiKey?: string
  qwenModel?: string
  qwenBaseUrl?: string
  researchEngineUrl?: string
  researchEngineToken?: string
  clearQwenApiKey?: boolean
  clearResearchEngineToken?: boolean
  clearResearchEngineUrl?: boolean
}

export interface ConnectionTestResult {
  target: 'qwen' | 'research_engine'
  success: boolean
  message: string
  statusCode?: number
}

export interface OriginalLiteraturePageSummary {
  pageNumber: number
  characterCount: number
  textSha256: string
}

export interface OriginalLiteratureDocument {
  documentId: string
  filename: string
  title: string
  author?: string
  sha256: string
  sizeBytes: number
  pageCount: number
  extractedPageCount: number
  extractedCharacterCount: number
  uploadedAt: string
  pages: OriginalLiteraturePageSummary[]
  isShowcase: boolean
  publicationYear?: number
  journal?: string
  doi?: string
  sourceUrl?: string
  license?: string
  showcaseOrder?: number
}

export interface OriginalLiteraturePage extends OriginalLiteraturePageSummary {
  text: string
}

export interface OriginalLiteratureAnswer {
  documentId: string
  documentSha256: string
  answer: string
  citedPages: number[]
  model: string
  usedPages: number[]
  usedCharacters: number
}

export interface BaselinePhase {
  id: string
  title: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
}

export interface BaselineRun {
  id: string
  systemId: 'agent_laboratory_social_science_adapted' | 'agent_laboratory_upstream_original'
  caseId: string
  caseName: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  phases: BaselinePhase[]
  executionStatus: string
  scientificStatus: string
  methodFamily?: string
  llmCalls: number
  inputTokens: number
  outputTokens: number
  wallTimeSeconds: number
  error?: string
  createdAt: string
  updatedAt: string
}

export interface KnowledgeSourceLocator {
  page_start?: number | null
  page_end?: number | null
  section?: string | null
  paragraph?: number | null
}

export interface KnowledgeEvidenceHit {
  document_id: string
  chunk_id: string
  title: string
  text: string
  source_type: string
  source_locator: KnowledgeSourceLocator
  source_url?: string | null
  doi?: string | null
  retrieval_score: number
  evidence_status: string
  publication_year?: number | null
}

export interface KnowledgeEvidenceBundle {
  schema_version: 'evidence-bundle/1.0.0'
  bundle_id: string
  question: string
  as_of: string
  generated_at: string
  corpus_snapshot_id: string
  evidence_hits: KnowledgeEvidenceHit[]
  graph_edges: Array<Record<string, unknown>>
  retrieval_diagnostics: {
    requested_top_k: number
    returned_hits: number
    unique_document_count: number
    max_hits_from_one_document: number
    diversity_mode: 'none' | 'per_document_cap'
    max_hits_per_document: number
    effective_min_unique_documents: number
    diversity_gate_passed: boolean
    skipped_by_document_cap: number
  }
  warnings: string[]
}

export interface KnowledgeCatalogDocument {
  document_id: string
  title: string
  title_source: 'metadata' | 'derived' | 'identifier'
  authors: string[]
  abstract?: string | null
  journal?: string | null
  doi?: string | null
  publication_year?: number | null
  has_fulltext: boolean
  content_kind: 'indexed_fulltext' | 'metadata_only'
  source_format: string
  access_level?: string | null
  original_pdf_available: boolean
  reading_available: boolean
}

export interface KnowledgeCatalogPage {
  corpus_snapshot_id: string
  total_documents: number
  fulltext_documents: number
  readable_documents: number
  metadata_only_documents: number
  declared_source_asset_documents: number
  available_source_asset_documents: number
  original_pdf_documents: number
  vector_count: number
  graph_document_count: number
  graph_edge_count: number
  matched_documents: number
  offset: number
  limit: number
  next_offset?: number | null
  data_updated_at?: string | null
  access_level?: string | null
  source_format_counts: Record<string, number>
  collection_status: 'snapshot_only' | 'connected'
  collection_message: string
  items: KnowledgeCatalogDocument[]
  warnings: string[]
}

export interface KnowledgeDocumentTextSlice {
  document_id: string
  title: string
  source_format: string
  access_level?: string | null
  content_sha256: string
  total_characters: number
  offset: number
  limit: number
  next_offset?: number | null
  text: string
}

export interface DiscoveryFindingDraft {
  key: string
  statement: string
  direction: 'positive' | 'negative' | 'null' | 'mixed' | 'nonlinear' | 'heterogeneous' | 'unknown'
  role: 'support' | 'challenge'
  evidence_chunk_ids: string[]
}

export interface DiscoveryConstructDraft {
  key: string
  label: string
  definition: string
  granularity: string
  role: 'predictor' | 'outcome' | 'mediator' | 'moderator' | 'control'
  expected_direction: 'positive' | 'negative' | 'nonlinear' | 'heterogeneous' | 'unspecified'
  evidence_chunk_ids: string[]
}

export interface DiscoveryPlanWire {
  schema_version: 'discovery-plan/1.0.0'
  field_label: string
  stream_label: string
  stream_description: string
  findings: DiscoveryFindingDraft[]
  constructs: DiscoveryConstructDraft[]
  gap_type: string
  gap_title: string
  gap_statement: string
  current_state: string
  missing_piece: string
  why_important: string
  candidate_research_question: string
  hypothesis_title: string
  hypothesis_statement: string
  falsifiable_form: string
  rationale: string
  mechanism_chain: Array<{
    source_key: string
    relation: string
    target_key: string
    statement: string
    evidence_chunk_ids: string[]
  }>
  predictions: Array<{
    key: string
    statement: string
    observable_pattern: string
    would_falsify: string
  }>
  boundary_conditions: string[]
  unresolved_conflicts: string[]
  unit_of_analysis: string
  baseline_specification: string
  major_threats: string[]
  required_inputs: string[]
  blocking_questions: string[]
  validation_acceptance_criteria: string[]
  novelty_queries: string[]
  novelty_remaining_difference: string
  scores: {
    novelty: number
    theory: number
    evidence: number
    data: number
    method: number
    policy_value: number
  }
  [key: string]: unknown
}

export interface DiscoveryPlanGeneration {
  originalQuestion: string
  evidenceBundle: KnowledgeEvidenceBundle
  plan: DiscoveryPlanWire
  modelUsage: Record<string, unknown>
  consistencyReview: QuestionPlanConsistencyReviewWire | null
  consistencyReviews: QuestionPlanConsistencyReviewWire[]
  retrievalRounds: DiscoveryRetrievalRoundWire[]
  repairCount: number
  finalConsistencyPassed: boolean
  executionReadiness: DiscoveryExecutionReadinessWire | null
  warnings: string[]
}

export interface QuestionPlanConsistencyReviewWire {
  schema_version: string
  decision: 'pass' | 'requery'
  exposure_preserved: boolean
  outcome_preserved: boolean
  qualifiers_preserved: boolean
  missing_concepts: string[]
  requery_terms: string[]
  rationale: string
}

export interface DiscoveryRetrievalRoundWire {
  round_index: number
  query: string
  bundle_id: string
  evidence_hit_count: number
  unique_document_count: number
  diversity_gate_passed: boolean
  candidate_research_question: string
  hypothesis_statement: string
  construct_labels: string[]
  consistency_decision: 'pass' | 'requery' | null
  repair_feedback_applied: boolean
  repair_directive_sha256?: string | null
}

export interface DiscoveryExecutionReadinessWire {
  schema_version: string
  status: 'ready' | 'blocked'
  can_execute: boolean
  dataset_candidates: Array<{
    candidate_id: string
    label: string
    status: 'ready' | 'blocked'
    blockers: string[]
  }>
  variable_dictionary: Array<{
    construct_key: string
    construct_label: string
    role: 'predictor' | 'outcome' | 'mediator' | 'moderator' | 'control'
    status: 'bound' | 'unbound'
    blocker?: string | null
  }>
  identification_strategies: Array<{
    strategy_id: string
    label: string
    status: 'candidate_ready_for_h1_review' | 'blocked'
    blocker?: string | null
  }>
  blockers: string[]
  warnings: string[]
}

export interface DiscoveryReleasePreviewWire {
  schema_version: string
  final_research_graph: Record<string, unknown>
  gap_cards: Array<Record<string, unknown>>
  hypothesis_cards: Array<Record<string, unknown>>
  validation_warnings: string[]
  reviewer: string
  review_note: string
  [key: string]: unknown
}

export interface DiscoveryLaunchResult {
  discoveryRelease: DiscoveryReleasePreviewWire
  run: RunSnapshot
}
