import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DATASET_FIXTURES,
  LITERATURE_FIXTURES,
  METHOD_FIXTURES,
  POLICY_FIXTURES,
  PRODUCT_STORE_KEY,
  PRODUCT_STORE_VERSION,
  MAX_LOCAL_PROJECTS,
  addProjectResource,
  buildDiscoveryHandoff,
  confirmScientificTen,
  createProject,
  deleteProjects,
  frontendDataSource,
  getEvidenceBundle,
  getProject,
  generateScientificFigures,
  generateScientificTen,
  migrateProductState,
  queryResources,
  readProductState,
  removeProjectResource,
  resetProductStore,
  selectDiscoveryIdea,
  setScientificFigureLanguage,
  setProductStorageForTests,
  subscribeProductStore,
  updateDiscoveryDraft,
  updateScientificFigureCopy,
  updateScientificTenItem,
} from '../src/product'
import {
  MOCK_TASK_STORE_KEY,
  MOCK_TASK_STORE_VERSION,
  MAX_LOCAL_DEMO_TASKS,
  SHOWCASE_TASK_ID,
} from '../src/data/mockPipeline'
import type { ProductStorage } from '../src/product'

class MemoryStorage implements ProductStorage {
  private values = new Map<string, string>()

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }
}

let storage: MemoryStorage

beforeEach(() => {
  storage = new MemoryStorage()
  vi.stubGlobal('localStorage', storage)
  setProductStorageForTests(storage)
  resetProductStore({ seed: false })
})

describe('versioned product store', () => {
  it('blocks new projects at the hard local limit without deleting existing data', () => {
    storage.setItem(PRODUCT_STORE_KEY, JSON.stringify({
      version: PRODUCT_STORE_VERSION,
      selectedProjectId: null,
      projects: Array.from({ length: MAX_LOCAL_PROJECTS }, (_, index) => ({
        id: `project-${index}`,
        title: `项目 ${index}`,
      })),
    }))

    expect(() => createProject({ title: '超限项目' })).toThrow(/50 个上限/)
    expect(readProductState().projects).toHaveLength(MAX_LOCAL_PROJECTS)
  })
  it('migrates an older project shape and persists the current version', () => {
    storage.setItem(PRODUCT_STORE_KEY, JSON.stringify({
      version: 0,
      selectedProjectId: 'legacy-project',
      projects: [{
        id: 'legacy-project',
        title: '旧项目',
        resources: [{ kind: 'policy', resourceId: 'policy-001' }],
        discovery: { currentStep: 2 },
      }],
    }))

    const state = readProductState()

    expect(state.version).toBe(PRODUCT_STORE_VERSION)
    expect(state.selectedProjectId).toBe('legacy-project')
    expect(state.projects.find((project) => project.id === 'legacy-project')).toMatchObject({
      id: 'legacy-project',
      mode: 'discovery_blind',
      status: 'draft',
    })
    expect(state.projects.find((project) => project.id === 'legacy-project')?.resources[0]).toMatchObject({
      projectId: 'legacy-project',
      kind: 'policy',
      resourceId: 'policy-001',
    })
    expect(JSON.parse(storage.getItem(PRODUCT_STORE_KEY) ?? '{}')).toMatchObject({
      version: PRODUCT_STORE_VERSION,
    })
  })

  it('resets to an empty test state and notifies subscribers', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeProductStore(listener)
    createProject({ title: '会被清除的项目' })

    resetProductStore({ seed: false })

    expect(readProductState()).toEqual({
      version: PRODUCT_STORE_VERSION,
      projects: [],
      selectedProjectId: null,
    })
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
  })

  it('returns a deterministic seed when migration input is invalid', () => {
    const migrated = migrateProductState(null)
    expect(migrated.projects[0]).toMatchObject({
      id: 'project-carbon-market-showcase',
      mode: 'discovery_blind',
      status: 'handoff_ready',
    })
  })

  it('deletes only selected projects and keeps a valid selected project', () => {
    const first = createProject({ title: '保留项目' })
    const second = createProject({ title: '删除项目' })

    expect(deleteProjects([second.id, 'missing-project'])).toBe(1)
    expect(getProject(second.id)).toBeNull()
    expect(getProject(first.id)?.title).toBe('保留项目')
    expect(readProductState().selectedProjectId).toBe(first.id)
  })
})

describe('project evidence bundle', () => {
  it('adds resources idempotently and removes only the requested link', () => {
    const project = createProject({ title: '资源篮测试', mode: 'reproduction_aligned' })

    const first = addProjectResource(project.id, 'literature', 'lit-001')
    const duplicate = addProjectResource(project.id, 'literature', 'lit-001')
    addProjectResource(project.id, 'method', 'method-001')

    expect(first).toEqual(duplicate)
    expect(getProject(project.id)?.mode).toBe('reproduction_aligned')
    expect(getProject(project.id)?.resources).toHaveLength(2)
    expect(removeProjectResource(project.id, 'literature', 'lit-001')).toBe(true)
    expect(removeProjectResource(project.id, 'literature', 'lit-001')).toBe(false)
    expect(getEvidenceBundle(project.id).counts).toEqual({
      literature: 0,
      policy: 0,
      dataset: 0,
      method: 1,
    })
  })

  it('rejects unknown catalog records', () => {
    const project = createProject({ title: '无效资源测试' })
    expect(addProjectResource(project.id, 'dataset', 'dataset-does-not-exist')).toBeNull()
    expect(getProject(project.id)?.resources).toEqual([])
  })
})

describe('resource catalog', () => {
  it('ships deterministic minimum fixture coverage without private asset references', () => {
    expect(LITERATURE_FIXTURES.length).toBeGreaterThanOrEqual(12)
    expect(POLICY_FIXTURES.length).toBeGreaterThanOrEqual(12)
    expect(DATASET_FIXTURES.length).toBeGreaterThanOrEqual(12)
    expect(METHOD_FIXTURES.length).toBeGreaterThanOrEqual(12)
    expect(JSON.stringify(LITERATURE_FIXTURES)).not.toMatch(/hidden_reference|restricted|\/Users\//i)
  })

  it('combines free-text search and attribute filters', () => {
    const policyPage = queryResources({
      kind: 'policy',
      search: '绿色',
      filters: { administrativeLevel: '国家', status: '现行' },
      pageSize: 50,
    })
    expect(policyPage.total).toBeGreaterThan(0)
    expect(policyPage.items.every((item) => (
      item.attributes.administrativeLevel === '国家'
      && item.attributes.status === '现行'
    ))).toBe(true)

    const datasetPage = queryResources({
      kind: 'dataset',
      filters: { variables: ['AQI', '不存在的变量'] },
    })
    expect(datasetPage.items.map((item) => item.id)).toEqual(['dataset-005'])
  })

  it('uses stable opaque cursors without duplicating rows', () => {
    const first = queryResources({ kind: 'method', pageSize: 5 })
    const second = queryResources({ kind: 'method', pageSize: 5, cursor: first.nextCursor })
    const third = queryResources({ kind: 'method', pageSize: 5, cursor: second.nextCursor })
    const ids = [...first.items, ...second.items, ...third.items].map((item) => item.id)

    expect(first.total).toBe(12)
    expect(first.hasMore).toBe(true)
    expect(third.nextCursor).toBeNull()
    expect(new Set(ids).size).toBe(12)
  })
})

describe('discovery handoff', () => {
  it('maps selected user-authored fields but never promotes catalog metadata to formal facts or files', () => {
    const project = createProject({
      title: '绿色政策研究',
      brief: {
        researchQuestion: '政策是否促进绿色创新？',
        unitOfAnalysis: '企业—年度',
        samplePeriod: '2015–2023',
        dataStructureHint: 'panel',
        constraints: ['只使用已授权输入。'],
      },
    })
    updateDiscoveryDraft(project.id, {
      ideaCards: [{
        id: 'idea-1',
        title: '政策冲击与创新',
        hypothesis: '政策促进企业绿色创新。',
        expectedDirection: 'positive',
        mechanism: '融资约束缓解。',
        variables: [{
          name: 'green_patent',
          label: '绿色专利',
          role: 'outcome',
          definition: '企业年度绿色专利数量',
          source: '用户填写的数据说明',
        }],
        pareto: {
          novelty: 4,
          feasibility: 3,
          identification: 4,
          dataReadiness: 2,
          policyValue: 5,
        },
      }],
    })
    selectDiscoveryIdea(project.id, 'idea-1')
    addProjectResource(project.id, 'policy', 'policy-001')
    addProjectResource(project.id, 'dataset', 'dataset-007')

    const handoff = buildDiscoveryHandoff(project.id)

    expect(handoff?.caseInput).toMatchObject({
      caseId: project.id,
      researchQuestion: '政策是否促进绿色创新？',
      hypotheses: [{ hypothesisId: 'idea-1', expectedDirection: 'positive' }],
      datasetRefs: [],
      knownPolicyFacts: [],
    })
    expect(handoff?.missingFields).toEqual(expect.arrayContaining([
      'variables.id',
      'variables.time',
      'datasetRefs',
      'knownPolicyFacts (requires human confirmation)',
    ]))
    expect(handoff?.evidenceBundle.counts).toMatchObject({ policy: 1, dataset: 1 })
    expect(handoff?.readyForFormalTask).toBe(false)
  })

  it('lists missing discovery fields on an incomplete draft', () => {
    const project = createProject({ title: '未完成研究' })
    expect(buildDiscoveryHandoff(project.id)?.missingFields).toEqual(expect.arrayContaining([
      'researchQuestion',
      'hypotheses',
      'unitOfAnalysis',
      'samplePeriod',
      'variables.outcome',
      'datasetRefs',
    ]))
  })
})

describe('scientific ten proposal', () => {
  function createProposalProject() {
    const project = createProject({
      title: '科学十项测试',
      brief: {
        researchQuestion: '政策是否改善企业创新？',
        goal: '形成可审查的因果研究方案。',
        unitOfAnalysis: '企业—年度',
        samplePeriod: '2018–2024',
        dataStructureHint: 'panel',
        constraints: ['只使用已授权输入。'],
      },
    })
    updateDiscoveryDraft(project.id, {
      gapCards: [{
        id: 'gap-ten',
        title: '机制证据仍不完整',
        evidence: '当前资源支持总体效应，但机制证据不足。',
        opportunity: '区分融资约束与创新激励路径。',
        resourceIds: ['lit-001'],
      }],
      ideaCards: [{
        id: 'idea-ten',
        title: '政策、融资约束与创新',
        hypothesis: '政策通过缓解融资约束促进企业创新。',
        expectedDirection: 'positive',
        mechanism: '融资约束缓解提高研发投入。',
        variables: [{
          name: 'innovation',
          label: '创新产出',
          role: 'outcome',
          definition: '企业年度专利产出',
          source: '待绑定的企业数据',
        }],
        pareto: {
          novelty: 4,
          feasibility: 3,
          identification: 4,
          dataReadiness: 2,
          policyValue: 5,
        },
      }],
    })
    selectDiscoveryIdea(project.id, 'idea-ten')
    addProjectResource(project.id, 'literature', 'lit-001')
    addProjectResource(project.id, 'dataset', 'dataset-001')
    addProjectResource(project.id, 'method', 'method-001')
    return project
  }

  it('generates ten evidence-bounded items and persists them with the project', () => {
    const project = createProposalProject()
    const generated = generateScientificTen(project.id)
    const proposal = generated?.discovery.scientificTen

    expect(proposal?.items).toHaveLength(10)
    expect(proposal?.sourceIdeaId).toBe('idea-ten')
    expect(proposal?.figureLanguage).toBe('zh')
    expect(proposal?.figures.map((figure) => figure.kind)).toEqual([
      'mechanism',
      'coefficient',
      'event_study',
      'trend',
    ])
    expect(proposal?.figures[0]).toMatchObject({
      role: 'research_design',
      dataStatus: 'project_bound',
    })
    expect(proposal?.figures[1]).toMatchObject({
      role: 'planned_result',
      dataStatus: 'awaiting_estimates',
    })
    expect(proposal?.figures[0].copy.zh.title).toContain('研究机制')
    expect(proposal?.figures[0].copy.en.title).toContain('Research mechanism')
    expect(proposal?.items.map((item) => item.itemNo)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(proposal?.items[1]).toMatchObject({
      title: '研究空白与贡献边界',
      status: 'evidence_bound',
    })
    expect(proposal?.items[6]).toMatchObject({
      title: '数据、授权与连接可行性',
      status: 'pending',
      confirmed: false,
    })
    expect(readProductState().projects[0].discovery.scientificTen?.items).toHaveLength(10)
  })

  it('requires every item confirmation, then invalidates confirmation after an edit', () => {
    const project = createProposalProject()
    generateScientificTen(project.id)

    expect(confirmScientificTen(project.id)).toBeNull()
    for (let itemNo = 1; itemNo <= 10; itemNo += 1) {
      expect(updateScientificTenItem(project.id, itemNo, { confirmed: true })).not.toBeNull()
    }

    const confirmed = confirmScientificTen(project.id)
    expect(confirmed?.discovery.scientificTen).toMatchObject({
      status: 'confirmed',
    })
    expect(confirmed?.discovery.completedSteps).toContain(6)

    updateScientificTenItem(project.id, 3, { content: '修订后的核心假设与证伪标准。' })
    const revised = getProject(project.id)
    expect(revised?.discovery.scientificTen).toMatchObject({ status: 'draft' })
    expect(revised?.discovery.scientificTen?.items[2].confirmed).toBe(false)
    expect(revised?.discovery.completedSteps).not.toContain(6)
  })

  it('invalidates a generated proposal when its evidence basket changes', () => {
    const project = createProposalProject()
    expect(generateScientificTen(project.id)?.discovery.scientificTen).toBeDefined()

    addProjectResource(project.id, 'policy', 'policy-001')

    expect(getProject(project.id)?.discovery.scientificTen).toBeUndefined()
  })

  it('adds figures to a legacy proposal and edits bilingual copy without invalidating confirmation', () => {
    const project = createProposalProject()
    const generated = generateScientificTen(project.id)
    const proposal = generated?.discovery.scientificTen
    expect(proposal).toBeDefined()
    updateDiscoveryDraft(project.id, {
      scientificTen: proposal ? { ...proposal, figures: [] } : undefined,
    })
    expect(generateScientificFigures(project.id)?.discovery.scientificTen?.figures).toHaveLength(4)

    for (let itemNo = 1; itemNo <= 10; itemNo += 1) {
      updateScientificTenItem(project.id, itemNo, { confirmed: true })
    }
    expect(confirmScientificTen(project.id)?.discovery.scientificTen?.status).toBe('confirmed')

    setScientificFigureLanguage(project.id, 'en')
    updateScientificFigureCopy(project.id, 'coefficient-plan', 'en', {
      title: 'Custom coefficient figure',
      legend: ['Estimate', '95% CI'],
    })
    const updated = getProject(project.id)?.discovery.scientificTen
    expect(updated?.figureLanguage).toBe('en')
    expect(updated?.figures[1].copy.en).toMatchObject({
      title: 'Custom coefficient figure',
      legend: ['Estimate', '95% CI'],
    })
    expect(updated?.status).toBe('confirmed')
  })
})

describe('frontend-only research flow', () => {
  it('blocks new demo tasks at the hard limit without pruning stored tasks', () => {
    const tasks = Array.from({ length: MAX_LOCAL_DEMO_TASKS }, (_, index) => ({
      id: `mock-${index}`,
      title: `任务 ${index}`,
      mode: 'discovery_blind',
      status: 'completed',
      createdAt: '2026-08-09T00:00:00.000Z',
      updatedAt: '2026-08-09T00:00:00.000Z',
      progressAt: '2026-08-09T00:00:00.000Z',
      stages: [],
    }))
    storage.setItem(MOCK_TASK_STORE_KEY, JSON.stringify({
      version: MOCK_TASK_STORE_VERSION,
      tasks,
    }))

    expect(() => frontendDataSource.createDemoTask('超限任务', 'discovery_blind'))
      .toThrow(/100 个上限/)
    expect(JSON.parse(storage.getItem(MOCK_TASK_STORE_KEY) ?? '{}').tasks)
      .toHaveLength(MAX_LOCAL_DEMO_TASKS)
  })

  it('persists a project, four-library basket, handoff, and demo task through the shared data source', () => {
    const project = frontendDataSource.createProject({
      title: '前端闭环测试',
      brief: {
        researchQuestion: '一项政策是否改善企业创新？',
        unitOfAnalysis: '企业—年度',
        samplePeriod: '2018–2024',
        dataStructureHint: 'panel',
      },
    })

    frontendDataSource.addProjectResource(project.id, 'literature', 'lit-001')
    frontendDataSource.addProjectResource(project.id, 'policy', 'policy-001')
    frontendDataSource.addProjectResource(project.id, 'dataset', 'dataset-001')
    frontendDataSource.addProjectResource(project.id, 'method', 'method-001')
    frontendDataSource.updateDiscoveryDraft(project.id, {
      gapCards: [{
        id: 'gap-flow',
        title: '机制证据缺口',
        evidence: '现有目录资源支持总体关系。',
        opportunity: '进一步检验作用机制。',
        resourceIds: ['lit-001', 'policy-001', 'dataset-001', 'method-001'],
      }],
      ideaCards: [{
        id: 'idea-flow',
        title: '政策与创新',
        hypothesis: '政策改善企业创新。',
        expectedDirection: 'positive',
        mechanism: '融资约束缓解。',
        variables: [
          {
            name: 'innovation',
            label: '创新产出',
            role: 'outcome',
            definition: '企业年度创新产出',
            source: '待与真实文件绑定',
          },
          {
            name: 'policy',
            label: '政策处理',
            role: 'treatment',
            definition: '政策处理状态',
            source: '待人工确认',
          },
        ],
        pareto: {
          novelty: 4,
          feasibility: 4,
          identification: 4,
          dataReadiness: 3,
          policyValue: 5,
        },
      }],
    })
    frontendDataSource.selectDiscoveryIdea(project.id, 'idea-flow')

    const handoff = frontendDataSource.buildDiscoveryHandoff(project.id)
    expect(handoff?.evidenceBundle.counts).toEqual({
      literature: 1,
      policy: 1,
      dataset: 1,
      method: 1,
    })
    expect(handoff?.caseInput.datasetRefs).toEqual([])
    expect(handoff?.caseInput.knownPolicyFacts).toEqual([])

    const task = frontendDataSource.createDemoTask(
      handoff?.caseInput.title ?? project.title,
      project.mode,
    )
    frontendDataSource.updateProject(project.id, {
      status: 'handoff_ready',
      taskIds: [task.id],
    })

    expect(frontendDataSource.getDemoTask(task.id)?.stages.map((stage) => stage.gate))
      .toEqual(expect.arrayContaining(['H1', 'H2', 'H3', 'H4']))
    expect(frontendDataSource.getProject(project.id)?.taskIds).toEqual([task.id])
    const mockStore = JSON.parse(storage.getItem(MOCK_TASK_STORE_KEY) ?? '{}') as {
      version?: number
      tasks?: Array<{ id: string }>
    }
    expect(mockStore.version).toBe(MOCK_TASK_STORE_VERSION)
    expect(mockStore.tasks?.map((candidate) => candidate.id)).toEqual(
      expect.arrayContaining([SHOWCASE_TASK_ID, task.id]),
    )
  })
})
