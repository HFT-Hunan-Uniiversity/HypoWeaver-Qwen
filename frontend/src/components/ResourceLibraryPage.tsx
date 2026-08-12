import {
  ArrowRight,
  BookOpenCheck,
  Building2,
  Check,
  ChevronRight,
  CircleSlash2,
  Database,
  FileSearch,
  FilterX,
  FolderHeart,
  Info,
  Landmark,
  Layers3,
  LibraryBig,
  ListFilter,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Tags,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  frontendDataSource,
  type Project,
  type ProjectResourceLink,
  type ResourceDetail,
  type ResourceKind,
  type ResourcePage,
  type ResourceQuery,
} from '../product'
import '../library.css'

const PAGE_SIZE = 6
const {
  addProjectResource,
  getEvidenceBundle,
  getResource,
  getSelectedProjectId,
  listProjects,
  queryResources,
  removeProjectResource,
  setSelectedProjectId,
  subscribe: subscribeProductStore,
} = frontendDataSource

const kindMeta: Record<ResourceKind, {
  label: string
  shortLabel: string
  description: string
  icon: typeof BookOpenCheck
}> = {
  literature: {
    label: '文献库',
    shortLabel: '文献',
    description: '检索经过脱敏整理的研究证据与结论边界。',
    icon: BookOpenCheck,
  },
  policy: {
    label: '政策库',
    shortLabel: '政策',
    description: '按机构、层级和地区梳理政策事实与时间边界。',
    icon: Landmark,
  },
  dataset: {
    label: '数据库',
    shortLabel: '数据',
    description: '评估数据来源、覆盖范围、变量与可访问性。',
    icon: Database,
  },
  method: {
    label: '方法库',
    shortLabel: '方法',
    description: '比较识别策略、适用数据结构与诊断要求。',
    icon: Layers3,
  },
}

const kindOrder: ResourceKind[] = ['literature', 'policy', 'dataset', 'method']

interface FilterDescriptor {
  key: string
  label: string
  aliases: string[]
}

const filterDescriptors: Record<ResourceKind, FilterDescriptor[]> = {
  literature: [
    { key: 'scope', label: '研究范围', aliases: ['scope', 'researchScope', 'coverage'] },
    { key: 'conclusion', label: '结论方向', aliases: ['conclusion', 'conclusionType', 'finding'] },
    { key: 'topic', label: '研究主题', aliases: ['topic', 'topics'] },
    { key: 'year', label: '发表年份', aliases: ['year', 'publicationYear'] },
    { key: 'journal', label: '期刊来源', aliases: ['journal'] },
  ],
  policy: [
    { key: 'issuer', label: '发布机构', aliases: ['issuer', 'issuingAgency', 'agency'] },
    { key: 'level', label: '行政层级', aliases: ['level', 'administrativeLevel'] },
    { key: 'region', label: '适用地区', aliases: ['region', 'coverageRegion'] },
    { key: 'topic', label: '政策主题', aliases: ['topic', 'topics'] },
    { key: 'effectiveDate', label: '生效时间', aliases: ['effectiveDate'] },
    { key: 'status', label: '当前状态', aliases: ['status'] },
  ],
  dataset: [
    { key: 'source', label: '数据来源', aliases: ['source', 'provider'] },
    { key: 'region', label: '覆盖地区', aliases: ['region', 'coverageRegion'] },
    { key: 'frequency', label: '数据频率', aliases: ['frequency'] },
    { key: 'coverage', label: '时间范围', aliases: ['coverage', 'period'] },
    { key: 'access', label: '访问方式', aliases: ['access', 'accessMode'] },
    { key: 'variables', label: '核心变量', aliases: ['variables'] },
    { key: 'license', label: '使用许可', aliases: ['license'] },
    { key: 'quality', label: '质量状态', aliases: ['quality', 'qualityStatus'] },
  ],
  method: [
    { key: 'family', label: '方法家族', aliases: ['family', 'methodFamily'] },
    { key: 'goal', label: '研究目标', aliases: ['goal', 'researchGoal'] },
    { key: 'dataStructure', label: '数据结构', aliases: ['dataStructure', 'structure'] },
    { key: 'assumption', label: '关键假设', aliases: ['assumption', 'identificationAssumption', 'identificationAssumptions'] },
    { key: 'diagnostics', label: '诊断要求', aliases: ['diagnostics'] },
  ],
}

const attributeLabels: Record<string, string> = {
  access: '访问方式',
  accessMode: '访问方式',
  administrativeLevel: '行政层级',
  agency: '发布机构',
  assumption: '识别假设',
  conclusion: '结论方向',
  conclusionType: '结论方向',
  coverage: '覆盖范围',
  coverageRegion: '覆盖地区',
  dataStructure: '数据结构',
  diagnostics: '诊断要求',
  effectiveDate: '生效时间',
  family: '方法家族',
  frequency: '更新频率',
  goal: '研究目标',
  identificationAssumption: '识别假设',
  identificationAssumptions: '识别假设',
  issuer: '发布机构',
  journal: '期刊',
  level: '行政层级',
  license: '许可',
  methodFamily: '方法家族',
  period: '时间范围',
  provider: '数据提供方',
  publicationYear: '发表年份',
  quality: '质量状态',
  qualityStatus: '质量状态',
  region: '地区',
  researchGoal: '研究目标',
  researchScope: '研究范围',
  scope: '研究范围',
  status: '状态',
  structure: '数据结构',
  topic: '主题',
  topics: '主题',
  variables: '核心变量',
  year: '年份',
}

const availabilityLabels: Record<string, string> = {
  available: '可使用',
  catalog_only: '仅目录',
  metadata_only: '仅元数据',
  open: '开放获取',
  restricted: '受限访问',
  unavailable: '暂不可用',
}

function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function valuesOf(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(valuesOf)
  if (value === null || value === undefined || value === '') return []
  if (typeof value === 'boolean') return [value ? '是' : '否']
  if (typeof value === 'string' || typeof value === 'number') return [String(value)]
  return []
}

function filterValues(resource: ResourceDetail, descriptor: FilterDescriptor): string[] {
  const attributes = recordOf(resource.attributes)
  for (const alias of descriptor.aliases) {
    if (alias === 'source') {
      const sourceValues = valuesOf(resource.source)
      if (sourceValues.length) return sourceValues
    }
    const values = valuesOf(attributes[alias])
    if (values.length) return values
  }
  if (descriptor.key === 'topic') return resource.tags
  return []
}

function projectLabel(project: Project): string {
  const value = recordOf(project)
  return String(value.title ?? value.name ?? value.id)
}

function collectResourceLinks(value: unknown, target: ProjectResourceLink[] = [], seen = new Set<unknown>()): ProjectResourceLink[] {
  if (!value || typeof value !== 'object' || seen.has(value)) return target
  seen.add(value)
  if (Array.isArray(value)) {
    value.forEach((item) => collectResourceLinks(item, target, seen))
    return target
  }
  const candidate = value as Record<string, unknown>
  if (
    typeof candidate.resourceId === 'string'
    && typeof candidate.kind === 'string'
    && kindOrder.includes(candidate.kind as ResourceKind)
  ) {
    target.push(candidate as unknown as ProjectResourceLink)
    return target
  }
  Object.values(candidate).forEach((item) => collectResourceLinks(item, target, seen))
  return target
}

function availabilityTone(availability: ResourceDetail['availability']): string {
  const value = String(availability)
  if (value === 'available' || value === 'open') return 'is-ready'
  if (value === 'unavailable') return 'is-unavailable'
  return 'is-limited'
}

function displayValue(value: unknown): string {
  const values = valuesOf(value)
  if (values.length) return values.join('、')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return '暂未提供'
}

export interface ResourceLibraryPageProps {
  kind: ResourceKind
  activeProjectId: string | null
  onKindChange: (kind: ResourceKind) => void
  onOpenProject: (projectId: string) => void
}

export function ResourceLibraryPage({
  kind,
  activeProjectId,
  onKindChange,
  onOpenProject,
}: ResourceLibraryPageProps) {
  const [revision, setRevision] = useState(0)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [page, setPage] = useState<ResourcePage>(() => queryResources({ kind, pageSize: PAGE_SIZE }))
  const [selectedResourceId, setSelectedResourceId] = useState<string | null>(null)
  const [selectedProjectId, setLocalProjectId] = useState<string | null>(
    () => activeProjectId ?? getSelectedProjectId(),
  )
  const [filterPanelOpen, setFilterPanelOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)

  useEffect(() => subscribeProductStore(() => setRevision((value) => value + 1)), [])

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 240)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    setFilters({})
    setSearchInput('')
    setSearch('')
    setSelectedResourceId(null)
    setDetailOpen(false)
  }, [kind])

  useEffect(() => {
    if (activeProjectId) setLocalProjectId(activeProjectId)
  }, [activeProjectId])

  const projects = useMemo(() => listProjects(), [revision])
  const effectiveProjectId = selectedProjectId && projects.some((project) => project.id === selectedProjectId)
    ? selectedProjectId
    : projects[0]?.id ?? null

  useEffect(() => {
    if (!selectedProjectId && effectiveProjectId) {
      setLocalProjectId(effectiveProjectId)
      setSelectedProjectId(effectiveProjectId)
    }
  }, [effectiveProjectId, selectedProjectId])

  const catalog = useMemo(
    () => queryResources({ kind, pageSize: 100 }).items,
    [kind],
  )
  const resolvedFilters = useMemo(() => {
    return filterDescriptors[kind].map((descriptor) => {
      const queryKey = descriptor.aliases.find((alias) => (
        catalog.some((resource) => valuesOf(recordOf(resource.attributes)[alias]).length > 0)
      )) ?? descriptor.key
      const values = new Set(catalog.flatMap((resource) => {
        const fromAttribute = valuesOf(recordOf(resource.attributes)[queryKey])
        return fromAttribute.length ? fromAttribute : filterValues(resource, descriptor)
      }))
      return { ...descriptor, queryKey, options: [...values].sort((a, b) => a.localeCompare(b, 'zh-CN')) }
    })
  }, [catalog, kind])
  const queryFilters = useMemo(() => Object.fromEntries(
    resolvedFilters
      .filter((descriptor) => filters[descriptor.key])
      .map((descriptor) => [descriptor.queryKey, filters[descriptor.key]]),
  ), [filters, resolvedFilters])
  const queryKey = JSON.stringify({ kind, search, filters: queryFilters })

  useEffect(() => {
    const query: ResourceQuery = {
      kind,
      search: search || undefined,
      filters: queryFilters,
      pageSize: PAGE_SIZE,
    }
    const nextPage = queryResources(query)
    setPage(nextPage)
    setSelectedResourceId((current) => (
      current && nextPage.items.some((item) => item.id === current)
        ? current
        : nextPage.items[0]?.id ?? null
    ))
  // queryKey is a stable serialization of the complete synchronous fixture query.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey])

  const bundleLinks = useMemo(() => (
    effectiveProjectId ? collectResourceLinks(getEvidenceBundle(effectiveProjectId)) : []
  ), [effectiveProjectId, revision])
  const basketResources = useMemo(() => (
    bundleLinks
      .map((link) => getResource(link.kind, link.resourceId))
      .filter((resource): resource is ResourceDetail => Boolean(resource))
  ), [bundleLinks])

  const selectedResource = selectedResourceId ? getResource(kind, selectedResourceId) : null
  const selectedIsInBasket = Boolean(selectedResource && bundleLinks.some(
    (link) => link.kind === selectedResource.kind && link.resourceId === selectedResource.id,
  ))
  const availableCount = catalog.filter((resource) => availabilityTone(resource.availability) === 'is-ready').length
  const activeFilterCount = Object.values(filters).filter(Boolean).length

  function selectProject(projectId: string) {
    setLocalProjectId(projectId)
    setSelectedProjectId(projectId)
  }

  function toggleResource(resource: ResourceDetail) {
    if (!effectiveProjectId) return
    const linked = bundleLinks.some((link) => link.kind === resource.kind && link.resourceId === resource.id)
    if (linked) removeProjectResource(effectiveProjectId, resource.kind, resource.id)
    else addProjectResource(effectiveProjectId, resource.kind, resource.id)
  }

  function clearFilters() {
    setFilters({})
    setSearchInput('')
    setSearch('')
  }

  function loadMore() {
    if (!page.nextCursor) return
    const next = queryResources({
      kind,
      search: search || undefined,
      filters: queryFilters,
      cursor: page.nextCursor,
      pageSize: PAGE_SIZE,
    })
    setPage({
      ...next,
      items: [...page.items, ...next.items],
      total: page.total,
    })
  }

  const KindIcon = kindMeta[kind].icon

  return (
    <section className="resource-library" aria-labelledby="resource-library-title">
      <header className="resource-library__header">
        <div className="resource-library__heading">
          <span className="resource-library__eyebrow">
            <LibraryBig size={14} aria-hidden="true" />
            研究资源库
          </span>
          <div className="resource-library__title-line">
            <h1 id="resource-library-title">{kindMeta[kind].label}</h1>
            <span className="resource-library__demo">
              <span aria-hidden="true" />
              前端演示 · 脱敏快照
            </span>
          </div>
          <p>{kindMeta[kind].description}</p>
        </div>
        <div className="resource-library__snapshot" role="note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span><strong>本地 fixture</strong><small>此页面不连接研究后端</small></span>
        </div>
      </header>

      <nav className="resource-library__tabs" aria-label="资源类型">
        {kindOrder.map((itemKind) => {
          const Icon = kindMeta[itemKind].icon
          return (
            <button
              type="button"
              key={itemKind}
              className={itemKind === kind ? 'is-active' : ''}
              aria-pressed={itemKind === kind}
              onClick={() => onKindChange(itemKind)}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{kindMeta[itemKind].shortLabel}</span>
            </button>
          )
        })}
      </nav>

      <div className="resource-library__metrics" aria-label={`${kindMeta[kind].label}概览`}>
        <div>
          <span>当前快照</span>
          <strong>{catalog.length}</strong>
          <small>条资源</small>
        </div>
        <div>
          <span>可直接访问</span>
          <strong>{availableCount}</strong>
          <small>条记录</small>
        </div>
        <div>
          <span>当前结果</span>
          <strong>{page.total}</strong>
          <small>条匹配</small>
        </div>
        <div className="is-basket">
          <span>项目资源篮</span>
          <strong>{basketResources.length}</strong>
          <small>{effectiveProjectId ? '已关联' : '未选择项目'}</small>
        </div>
      </div>

      <div className="resource-library__body">
        {filterPanelOpen && (
          <button
            type="button"
            className="resource-library__filter-scrim"
            aria-label="关闭筛选面板"
            onClick={() => setFilterPanelOpen(false)}
          />
        )}

        <aside className={`resource-library__filters ${filterPanelOpen ? 'is-open' : ''}`} aria-label="资源筛选">
          <div className="resource-library__pane-head">
            <span><SlidersHorizontal size={15} aria-hidden="true" />筛选</span>
            <button type="button" aria-label="关闭筛选面板" onClick={() => setFilterPanelOpen(false)}>
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          <label className="resource-library__search">
            <span className="sr-only">搜索{kindMeta[kind].label}</span>
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder={`搜索${kindMeta[kind].shortLabel}标题、摘要或标签`}
            />
            {searchInput && (
              <button type="button" aria-label="清空搜索" onClick={() => setSearchInput('')}>
                <X size={14} aria-hidden="true" />
              </button>
            )}
          </label>

          <div className="resource-library__filter-fields">
            {resolvedFilters.map((descriptor) => (
              <label key={descriptor.key}>
                <span>{descriptor.label}</span>
                <select
                  value={filters[descriptor.key] ?? ''}
                  onChange={(event) => setFilters((current) => ({
                    ...current,
                    [descriptor.key]: event.target.value,
                  }))}
                >
                  <option value="">全部</option>
                  {descriptor.options.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>

          {(activeFilterCount > 0 || searchInput) && (
            <button type="button" className="resource-library__clear" onClick={clearFilters}>
              <FilterX size={14} aria-hidden="true" />
              清除全部条件
            </button>
          )}

          {kind === 'literature' && (
            <section className="resource-library__method-note" aria-labelledby="screening-method-title">
              <span className="resource-library__note-icon"><FileSearch size={16} aria-hidden="true" /></span>
              <div>
                <p>筛选方法</p>
                <h2 id="screening-method-title">证据范围与结论双重编码</h2>
                <ul>
                  <li>先按研究对象、地区与年份界定范围。</li>
                  <li>再区分正向、负向、混合及不显著结论。</li>
                  <li>快照只保留公开元数据与脱敏摘要。</li>
                </ul>
              </div>
            </section>
          )}

          <section className="resource-library__basket" aria-labelledby="resource-basket-title">
            <div className="resource-library__basket-head">
              <span>
                <FolderHeart size={15} aria-hidden="true" />
                <strong id="resource-basket-title">项目资源篮</strong>
              </span>
              <small>{basketResources.length}</small>
            </div>

            <label>
              <span className="sr-only">选择资源所属项目</span>
              <select
                value={effectiveProjectId ?? ''}
                disabled={projects.length === 0}
                onChange={(event) => selectProject(event.target.value)}
              >
                {projects.length === 0 && <option value="">暂无项目</option>}
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{projectLabel(project)}</option>
                ))}
              </select>
            </label>

            {basketResources.length > 0 ? (
              <div className="resource-library__basket-list">
                {basketResources.slice(0, 4).map((resource) => (
                  <div key={`${resource.kind}:${resource.id}`}>
                    <span>{kindMeta[resource.kind].shortLabel}</span>
                    <strong title={resource.title}>{resource.title}</strong>
                    <button
                      type="button"
                      aria-label={`从项目资源篮移除${resource.title}`}
                      onClick={() => effectiveProjectId && removeProjectResource(effectiveProjectId, resource.kind, resource.id)}
                    >
                      <X size={13} aria-hidden="true" />
                    </button>
                  </div>
                ))}
                {basketResources.length > 4 && <small>另有 {basketResources.length - 4} 条资源</small>}
              </div>
            ) : (
              <p className="resource-library__basket-empty">从结果中选择资源，先加入项目证据包，再进入研究发现流程。</p>
            )}

            {effectiveProjectId && (
              <button
                type="button"
                className="resource-library__open-project"
                onClick={() => onOpenProject(effectiveProjectId)}
              >
                查看项目
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            )}
          </section>
        </aside>

        <main className="resource-library__results">
          <div className="resource-library__result-toolbar">
            <button
              type="button"
              className="resource-library__filter-toggle"
              aria-expanded={filterPanelOpen}
              onClick={() => setFilterPanelOpen(true)}
            >
              <ListFilter size={15} aria-hidden="true" />
              筛选
              {activeFilterCount > 0 && <span>{activeFilterCount}</span>}
            </button>
            <p aria-live="polite">
              <strong>{page.total}</strong> 条结果
              {search && <span> · “{search}”</span>}
            </p>
            <small>按快照收录顺序</small>
          </div>

          {page.items.length > 0 ? (
            <>
              <div className="resource-library__list" role="list">
                {page.items.map((resource) => {
                  const inBasket = bundleLinks.some(
                    (link) => link.kind === resource.kind && link.resourceId === resource.id,
                  )
                  return (
                    <article
                      key={resource.id}
                      role="listitem"
                      className={`resource-library__card ${selectedResourceId === resource.id ? 'is-selected' : ''}`}
                    >
                      <button
                        type="button"
                        className="resource-library__card-main"
                        aria-current={selectedResourceId === resource.id ? 'true' : undefined}
                        onClick={() => {
                          setSelectedResourceId(resource.id)
                          setDetailOpen(true)
                        }}
                      >
                        <span className="resource-library__kind-icon"><KindIcon size={17} aria-hidden="true" /></span>
                        <span className="resource-library__card-copy">
                          <span className="resource-library__card-topline">
                            <span className={`resource-library__availability ${availabilityTone(resource.availability)}`}>
                              {availabilityLabels[String(resource.availability)] ?? String(resource.availability)}
                            </span>
                            <small>{resource.source}</small>
                          </span>
                          <strong>{resource.title}</strong>
                          <span className="resource-library__summary">
                            {resource.summary || '该条目暂未提供摘要，请在详情中查看已收录的结构化元数据。'}
                          </span>
                          <span className="resource-library__tags">
                            {resource.tags.slice(0, 3).map((tag) => <em key={tag}>{tag}</em>)}
                          </span>
                        </span>
                        <ChevronRight size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className={`resource-library__quick-add ${inBasket ? 'is-added' : ''}`}
                        disabled={!effectiveProjectId}
                        aria-label={inBasket ? `从项目资源篮移除${resource.title}` : `将${resource.title}加入项目资源篮`}
                        onClick={() => toggleResource(resource)}
                      >
                        {inBasket ? <Check size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
                        {inBasket ? '已加入' : '加入资源篮'}
                      </button>
                    </article>
                  )
                })}
              </div>
              {page.nextCursor && (
                <button type="button" className="resource-library__load-more" onClick={loadMore}>
                  加载更多
                  <span>{page.items.length} / {page.total}</span>
                </button>
              )}
            </>
          ) : (
            <div className="resource-library__empty">
              <span><CircleSlash2 size={25} aria-hidden="true" /></span>
              <h2>没有符合条件的资源</h2>
              <p>换一个关键词或减少筛选条件。当前筛选不会影响项目资源篮中的记录。</p>
              <button type="button" onClick={clearFilters}>
                <FilterX size={15} aria-hidden="true" />
                重置筛选
              </button>
            </div>
          )}
        </main>

        <aside
          className={`resource-library__detail ${detailOpen ? 'is-open' : ''}`}
          aria-label="资源详情"
          aria-hidden={!selectedResource}
        >
          {selectedResource ? (
            <>
              <div className="resource-library__detail-head">
                <span><KindIcon size={16} aria-hidden="true" />资源详情</span>
                <button type="button" aria-label="关闭资源详情" onClick={() => setDetailOpen(false)}>
                  <X size={17} aria-hidden="true" />
                </button>
              </div>
              <div className="resource-library__detail-scroll">
                <div className="resource-library__detail-title">
                  <span className={`resource-library__availability ${availabilityTone(selectedResource.availability)}`}>
                    {availabilityLabels[String(selectedResource.availability)] ?? String(selectedResource.availability)}
                  </span>
                  <h2>{selectedResource.title}</h2>
                  <p>{selectedResource.summary || '此条目暂未提供摘要；现阶段只展示可验证的结构化元数据。'}</p>
                </div>

                <dl className="resource-library__facts">
                  <div>
                    <dt><Building2 size={13} aria-hidden="true" />来源</dt>
                    <dd>{selectedResource.source}</dd>
                  </div>
                  {Object.entries(recordOf(selectedResource.attributes)).map(([key, value]) => (
                    <div key={key}>
                      <dt>{attributeLabels[key] ?? key}</dt>
                      <dd>{displayValue(value)}</dd>
                    </div>
                  ))}
                </dl>

                <section className="resource-library__detail-tags">
                  <h3><Tags size={14} aria-hidden="true" />主题标签</h3>
                  <div>{selectedResource.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                </section>

                {selectedResource.kind === 'dataset' && (
                  <div className="resource-library__boundary-note">
                    <Info size={16} aria-hidden="true" />
                    <p><strong>数据边界</strong>加入资源篮只保存目录引用；未实际导入且缺少文件名、哈希和大小的条目不会进入正式任务的 datasetRefs。</p>
                  </div>
                )}
                {selectedResource.kind === 'policy' && (
                  <div className="resource-library__boundary-note">
                    <Info size={16} aria-hidden="true" />
                    <p><strong>确认边界</strong>政策摘要需由研究者确认，才会在交接阶段转成 knownPolicyFacts。</p>
                  </div>
                )}
              </div>
              <div className="resource-library__detail-actions">
                <button
                  type="button"
                  className={selectedIsInBasket ? 'is-added' : ''}
                  disabled={!effectiveProjectId}
                  onClick={() => toggleResource(selectedResource)}
                >
                  {selectedIsInBasket ? <Check size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
                  {selectedIsInBasket ? '已加入项目资源篮' : '加入项目资源篮'}
                </button>
                {!effectiveProjectId && <small>请先创建或选择项目</small>}
              </div>
            </>
          ) : (
            <div className="resource-library__detail-empty">
              <FileSearch size={24} aria-hidden="true" />
              <p>选择一条资源查看详情</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}
