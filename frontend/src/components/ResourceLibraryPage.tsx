import {
  ArrowRight,
  BookOpenCheck,
  Building2,
  Check,
  ChevronRight,
  CircleSlash2,
  CloudOff,
  Database,
  FileCheck2,
  FileSearch,
  FileText,
  FilterX,
  FolderHeart,
  Info,
  Landmark,
  Layers3,
  LibraryBig,
  ListFilter,
  Network,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Tags,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import {
  frontendDataSource,
  type Project,
  type ProjectResourceLink,
  type ResourceDetail,
  type ResourceKind,
  type ResourcePage,
  type ResourceQuery,
} from '../product'
import { workflowApi } from '../runtime/api'
import type {
  KnowledgeCatalogDocument,
  KnowledgeCatalogPage,
  KnowledgeDocumentTextSlice,
  KnowledgeEvidenceBundle,
  KnowledgeEvidenceHit,
  OriginalLiteratureDocument,
} from '../runtime/types'
import { POLICY_DOCUMENTS } from '../data/policyDocuments'
import '../library.css'

const PAGE_SIZE = 6
const KNOWLEDGE_PAGE_SIZE = 12
type LiteratureShelf = 'system' | 'uploads'
const showcasePdfMetadata: Record<string, { order: number; year: number; journal: string; license: string }> = {
  'green-finance-environmental-violations-jfr.pdf': { order: 1, year: 2024, journal: '金融研究', license: '期刊官网公开全文' },
  'corporate-green-bonds-jfe.pdf': { order: 2, year: 2021, journal: 'Journal of Financial Economics', license: '作者公开全文' },
  'carbon-risk-jfe.pdf': { order: 3, year: 2021, journal: 'Journal of Financial Economics', license: 'NBER 公开工作论文' },
  'green-finance-air-quality.pdf': { order: 4, year: 2023, journal: 'Sustainability', license: 'CC BY 4.0' },
  'green-finance-green-innovation.pdf': { order: 5, year: 2022, journal: 'IJERPH', license: 'CC BY 4.0' },
  'green-finance-enterprise-technology.pdf': { order: 6, year: 2022, journal: 'Sustainability', license: 'CC BY 4.0' },
}
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
  documentNumber: '文号',
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

function formatBytes(value: number): string {
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`
}

function isShowcasePdf(document: OriginalLiteratureDocument): boolean {
  return Boolean(document.isShowcase || showcasePdfMetadata[document.filename])
}

function uploadErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '上传原始 PDF 失败。'
}

function knowledgeErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '系统论文库暂时不可用。'
}

function formatSnapshotDate(value?: string | null): string {
  if (!value) return '时间未记录'
  const date = new Date(value.replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(date)
}

function sourceFormatLabel(value: string): string {
  const labels: Record<string, string> = {
    feed_api: '题录元数据',
    txt: '正文文本 TXT',
    xml: '正文文本 XML',
    paper: '论文记录',
    metadata: '题录元数据',
    indexed_text: '正文文本',
  }
  return labels[value] ?? value
}

export interface ResourceLibraryPageProps {
  kind: ResourceKind
  activeProjectId: string | null
  onKindChange: (kind: ResourceKind) => void
  onOpenProject: (projectId: string) => void
  onOpenReader: (resourceId: string) => void
}

export function ResourceLibraryPage({
  kind,
  activeProjectId,
  onKindChange,
  onOpenProject,
  onOpenReader,
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
  const [originalDocuments, setOriginalDocuments] = useState<OriginalLiteratureDocument[]>([])
  const [originalDocumentsLoading, setOriginalDocumentsLoading] = useState(false)
  const [uploadingPdf, setUploadingPdf] = useState(false)
  const [pdfError, setPdfError] = useState('')
  const [literatureShelf, setLiteratureShelf] = useState<LiteratureShelf>('system')
  const [knowledgeCatalog, setKnowledgeCatalog] = useState<KnowledgeCatalogPage | null>(null)
  const [knowledgeBundle, setKnowledgeBundle] = useState<KnowledgeEvidenceBundle | null>(null)
  const [knowledgeQuery, setKnowledgeQuery] = useState('')
  const [knowledgeFulltextOnly, setKnowledgeFulltextOnly] = useState(true)
  const [knowledgeLoading, setKnowledgeLoading] = useState(false)
  const [knowledgeError, setKnowledgeError] = useState('')
  const [selectedKnowledgeDocument, setSelectedKnowledgeDocument] = useState<KnowledgeCatalogDocument | null>(null)
  const [selectedKnowledgeHit, setSelectedKnowledgeHit] = useState<KnowledgeEvidenceHit | null>(null)
  const [knowledgeReader, setKnowledgeReader] = useState<KnowledgeDocumentTextSlice | null>(null)
  const [knowledgeReaderOpen, setKnowledgeReaderOpen] = useState(false)
  const [policyReaderOpen, setPolicyReaderOpen] = useState(false)
  const [knowledgeReaderLoading, setKnowledgeReaderLoading] = useState(false)
  const [knowledgeReaderError, setKnowledgeReaderError] = useState('')
  const [pendingPdfDelete, setPendingPdfDelete] = useState<OriginalLiteratureDocument | null>(null)
  const [deletingPdfId, setDeletingPdfId] = useState<string | null>(null)
  const pdfInputRef = useRef<HTMLInputElement>(null)

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
    setPolicyReaderOpen(false)
  }, [kind])

  useEffect(() => {
    if (activeProjectId) setLocalProjectId(activeProjectId)
  }, [activeProjectId])

  useEffect(() => {
    if (kind !== 'literature') return
    let cancelled = false
    setOriginalDocumentsLoading(true)
    setPdfError('')
    workflowApi.listLiteratureDocuments()
      .then((documents) => { if (!cancelled) setOriginalDocuments(documents) })
      .catch((error) => { if (!cancelled) setPdfError(uploadErrorMessage(error)) })
      .finally(() => { if (!cancelled) setOriginalDocumentsLoading(false) })
    return () => { cancelled = true }
  }, [kind])

  useEffect(() => {
    if (kind !== 'literature') return
    let cancelled = false
    setKnowledgeLoading(true)
    setKnowledgeError('')
    workflowApi.getKnowledgeCatalog({
      fulltextOnly: true,
      readableOnly: true,
      limit: KNOWLEDGE_PAGE_SIZE,
    })
      .then((catalogPage) => {
        if (cancelled) return
        setKnowledgeCatalog(catalogPage)
        setSelectedKnowledgeDocument(catalogPage.items[0] ?? null)
      })
      .catch((error) => { if (!cancelled) setKnowledgeError(knowledgeErrorMessage(error)) })
      .finally(() => { if (!cancelled) setKnowledgeLoading(false) })
    return () => { cancelled = true }
  }, [kind])

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
    setSelectedResourceId((current) => kind === 'literature'
      ? null
      : current && nextPage.items.some((item) => item.id === current)
        ? current
        : nextPage.items[0]?.id ?? null
    )
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
  const selectedPolicyDocument = selectedResource ? POLICY_DOCUMENTS[selectedResource.id] : undefined
  const selectedIsInBasket = Boolean(selectedResource && bundleLinks.some(
    (link) => link.kind === selectedResource.kind && link.resourceId === selectedResource.id,
  ))
  const availableCount = catalog.filter((resource) => availabilityTone(resource.availability) === 'is-ready').length
  const activeFilterCount = Object.values(filters).filter(Boolean).length
  const showFixtureResults = kind !== 'literature'
  const knowledgeHits = knowledgeBundle?.evidence_hits ?? []
  const showcaseDocuments = useMemo(
    () => originalDocuments
      .filter(isShowcasePdf)
      .sort((left, right) => (
        left.showcaseOrder ?? showcasePdfMetadata[left.filename]?.order ?? 999
      ) - (
        right.showcaseOrder ?? showcasePdfMetadata[right.filename]?.order ?? 999
      )),
    [originalDocuments],
  )
  const uploadedDocuments = useMemo(
    () => originalDocuments.filter((item) => !isShowcasePdf(item)),
    [originalDocuments],
  )
  const knowledgeWarnings = knowledgeCatalog?.warnings.filter((warning) => (
    !warning.includes('source assets are absent')
  )) ?? []

  async function uploadOriginalPdf(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setUploadingPdf(true)
    setPdfError('')
    try {
      const uploaded = await workflowApi.uploadLiteratureDocument(file)
      setOriginalDocuments((current) => [uploaded, ...current.filter((item) => item.documentId !== uploaded.documentId)])
      onOpenReader(uploaded.documentId)
    } catch (error) {
      setPdfError(uploadErrorMessage(error))
    } finally {
      setUploadingPdf(false)
    }
  }

  async function deleteOriginalPdf() {
    if (!pendingPdfDelete) return
    setDeletingPdfId(pendingPdfDelete.documentId)
    setPdfError('')
    try {
      await workflowApi.deleteLiteratureDocument(pendingPdfDelete.documentId)
      setOriginalDocuments((current) => current.filter((item) => item.documentId !== pendingPdfDelete.documentId))
      setPendingPdfDelete(null)
    } catch (error) {
      setPdfError(error instanceof Error ? error.message : '删除原始 PDF 失败。')
      setPendingPdfDelete(null)
    } finally {
      setDeletingPdfId(null)
    }
  }

  async function openKnowledgeReader(documentId: string) {
    setKnowledgeReaderOpen(true)
    setKnowledgeReaderLoading(true)
    setKnowledgeReaderError('')
    setKnowledgeReader(null)
    try {
      setKnowledgeReader(await workflowApi.getKnowledgeDocumentText(documentId))
    } catch (error) {
      setKnowledgeReaderError(knowledgeErrorMessage(error))
    } finally {
      setKnowledgeReaderLoading(false)
    }
  }

  async function loadMoreKnowledgeText() {
    if (!knowledgeReader?.next_offset) return
    setKnowledgeReaderLoading(true)
    setKnowledgeReaderError('')
    try {
      const next = await workflowApi.getKnowledgeDocumentText(knowledgeReader.document_id, {
        offset: knowledgeReader.next_offset,
      })
      setKnowledgeReader({
        ...next,
        offset: 0,
        text: `${knowledgeReader.text}${next.text}`,
      })
    } catch (error) {
      setKnowledgeReaderError(knowledgeErrorMessage(error))
    } finally {
      setKnowledgeReaderLoading(false)
    }
  }

  async function refreshKnowledgeCatalog(offset = 0, append = false) {
    setKnowledgeLoading(true)
    setKnowledgeError('')
    try {
      const catalogPage = await workflowApi.getKnowledgeCatalog({
        query: knowledgeQuery,
        fulltextOnly: knowledgeFulltextOnly,
        readableOnly: knowledgeFulltextOnly,
        offset,
        limit: KNOWLEDGE_PAGE_SIZE,
      })
      setKnowledgeCatalog((current) => {
        if (!append || !current) return catalogPage
        const seen = new Set(current.items.map((item) => item.document_id))
        return {
          ...catalogPage,
          items: [...current.items, ...catalogPage.items.filter((item) => !seen.has(item.document_id))],
        }
      })
      if (!append) {
        setKnowledgeBundle(null)
        setSelectedKnowledgeHit(null)
        setSelectedKnowledgeDocument(catalogPage.items[0] ?? null)
      }
    } catch (error) {
      setKnowledgeError(knowledgeErrorMessage(error))
    } finally {
      setKnowledgeLoading(false)
    }
  }

  async function searchKnowledgeCorpus() {
    const question = knowledgeQuery.trim()
    if (!question) {
      await refreshKnowledgeCatalog()
      return
    }
    if (question.length < 2) {
      setKnowledgeError('请输入至少 2 个字符后再检索系统论文库。')
      return
    }
    setKnowledgeLoading(true)
    setKnowledgeError('')
    try {
      const [catalogPage, bundle] = await Promise.all([
        workflowApi.getKnowledgeCatalog({
          query: question,
          fulltextOnly: knowledgeFulltextOnly,
          readableOnly: knowledgeFulltextOnly,
          limit: KNOWLEDGE_PAGE_SIZE,
        }),
        workflowApi.searchKnowledge(question, {
          fulltextOnly: knowledgeFulltextOnly,
          topK: KNOWLEDGE_PAGE_SIZE,
        }),
      ])
      setKnowledgeCatalog(catalogPage)
      setKnowledgeBundle(bundle)
      setSelectedKnowledgeHit(bundle.evidence_hits[0] ?? null)
      setSelectedKnowledgeDocument(bundle.evidence_hits.length ? null : catalogPage.items[0] ?? null)
      setDetailOpen(Boolean(bundle.evidence_hits[0] ?? catalogPage.items[0]))
    } catch (error) {
      setKnowledgeError(knowledgeErrorMessage(error))
    } finally {
      setKnowledgeLoading(false)
    }
  }

  function submitKnowledgeSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void searchKnowledgeCorpus()
  }

  function switchLiteratureShelf(next: LiteratureShelf) {
    setLiteratureShelf(next)
    setDetailOpen(false)
    setKnowledgeReaderOpen(false)
    setPendingPdfDelete(null)
    setSelectedResourceId(null)
  }

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
          </div>
          <p>{kind === 'literature' ? '浏览系统论文、按研究主题检索，或上传自己的原始 PDF 让 AI 按页阅读。' : kindMeta[kind].description}</p>
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

      {kind === 'literature' && (
        <nav className="resource-library__shelves" aria-label="文献库内容分区">
          <button
            type="button"
            className={literatureShelf === 'system' ? 'is-active' : ''}
            onClick={() => switchLiteratureShelf('system')}
          >
            <Network size={15} aria-hidden="true" />
            <span>系统论文库</span>
            <small>{knowledgeCatalog?.total_documents ?? '—'}</small>
          </button>
          <button
            type="button"
            className={literatureShelf === 'uploads' ? 'is-active' : ''}
            onClick={() => switchLiteratureShelf('uploads')}
          >
            <FileCheck2 size={15} aria-hidden="true" />
            <span>上传我的 PDF</span>
            <small>{uploadedDocuments.length}</small>
          </button>
        </nav>
      )}

      <div className="resource-library__metrics" aria-label={`${kindMeta[kind].label}概览`}>
        {kind === 'literature' && literatureShelf === 'system' ? (
          <>
            <div><span>系统收录</span><strong>{knowledgeCatalog?.total_documents ?? '—'}</strong><small>篇论文记录</small></div>
            <div><span>可阅读正文</span><strong>{knowledgeCatalog?.readable_documents ?? '—'}</strong><small>篇支持在线阅读</small></div>
            <div><span>正文片段</span><strong>{knowledgeCatalog?.vector_count ?? '—'}</strong><small>条可用于主题检索</small></div>
            <div className="is-basket"><span>关联线索</span><strong>{knowledgeCatalog?.graph_edge_count ?? '—'}</strong><small>条辅助发现</small></div>
          </>
        ) : kind === 'literature' && literatureShelf === 'uploads' ? (
          <>
            <div><span>已上传原始 PDF</span><strong>{uploadedDocuments.length}</strong><small>份文件</small></div>
            <div><span>可 AI 阅读</span><strong>{uploadedDocuments.filter((item) => item.extractedPageCount > 0).length}</strong><small>份含文本层</small></div>
            <div><span>原始页数</span><strong>{uploadedDocuments.reduce((sum, item) => sum + item.pageCount, 0)}</strong><small>页可定位</small></div>
            <div className="is-basket"><span>当前项目资料</span><strong>{basketResources.length}</strong><small>{effectiveProjectId ? '已关联' : '未选择项目'}</small></div>
          </>
        ) : (
          <>
            <div><span>当前快照</span><strong>{catalog.length}</strong><small>条资源</small></div>
            <div><span>可直接访问</span><strong>{availableCount}</strong><small>条记录</small></div>
            <div><span>当前结果</span><strong>{page.total}</strong><small>条匹配</small></div>
            <div className="is-basket"><span>当前项目资料</span><strong>{basketResources.length}</strong><small>{effectiveProjectId ? '已关联' : '未选择项目'}</small></div>
          </>
        )}
      </div>

      <div className={`resource-library__body ${detailOpen ? 'has-detail' : 'without-detail'}`}>
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

          {showFixtureResults && <>
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
          </>}

          {kind === 'literature' && (
            <section className="resource-library__method-note" aria-labelledby="screening-method-title">
              <span className="resource-library__note-icon"><FileSearch size={16} aria-hidden="true" /></span>
              <div>
                <p>怎么使用</p>
                <h2 id="screening-method-title">
                  {literatureShelf === 'system' ? '先按主题检索，再打开单篇阅读' : '上传原始 PDF，让 AI 按页读'}
                </h2>
                {literatureShelf === 'system' ? (
                  <ul>
                    <li>输入研究主题、变量或方法，快速缩小阅读范围。</li>
                    <li>带“可阅读正文”的论文可以直接打开阅读全文。</li>
                    <li>需要核对版式、图表和页码时，再使用原始 PDF。</li>
                  </ul>
                ) : (
                  <ul>
                    <li>支持带文本层、未加密的论文 PDF。</li>
                    <li>可以按整篇或指定页面向 AI 提问。</li>
                    <li>回答会标注对应的原始 PDF 页码。</li>
                  </ul>
                )}
              </div>
            </section>
          )}

          <section className="resource-library__basket" aria-labelledby="resource-basket-title">
            <div className="resource-library__basket-head">
              <span>
                <FolderHeart size={15} aria-hidden="true" />
                <strong id="resource-basket-title">当前项目资料</strong>
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
                      aria-label={`从当前项目移除${resource.title}`}
                      onClick={() => effectiveProjectId && removeProjectResource(effectiveProjectId, resource.kind, resource.id)}
                    >
                      <X size={13} aria-hidden="true" />
                    </button>
                  </div>
                ))}
                {basketResources.length > 4 && <small>另有 {basketResources.length - 4} 条资源</small>}
              </div>
            ) : (
              <p className="resource-library__basket-empty">把需要的论文、政策、数据和方法加入当前项目，后续研究流程会自动引用。</p>
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
          {kind === 'literature' && literatureShelf === 'system' && (
            <section className="resource-library__system" aria-labelledby="system-library-title">
              <div className="resource-library__system-head">
                <div>
                  <span><Network size={16} aria-hidden="true" />论文发现与阅读</span>
                  <h2 id="system-library-title">检索研究主题，打开论文开始阅读</h2>
                  <p>
                    论文库更新于 {formatSnapshotDate(knowledgeCatalog?.data_updated_at)}；
                    可按主题检索正文片段，也可以直接打开单篇可用正文。
                  </p>
                </div>
                <button type="button" disabled={knowledgeLoading} onClick={() => void searchKnowledgeCorpus()}>
                  <RefreshCw size={14} aria-hidden="true" />
                  刷新
                </button>
              </div>

              <div className="resource-library__system-boundaries" aria-label="系统论文库收录概览">
                <div className="is-positive">
                  <FileText size={16} aria-hidden="true" />
                  <span><strong>{knowledgeCatalog?.readable_documents ?? '—'} 篇</strong>可打开正文阅读</span>
                </div>
                <div>
                  <FileCheck2 size={16} aria-hidden="true" />
                  <span><strong>{knowledgeCatalog ? knowledgeCatalog.fulltext_documents - knowledgeCatalog.readable_documents : '—'} 篇</strong>已建立检索索引</span>
                </div>
                <div>
                  <Database size={16} aria-hidden="true" />
                  <span><strong>{knowledgeCatalog?.metadata_only_documents ?? '—'} 篇</strong>题录与摘要</span>
                </div>
              </div>

                <div className="resource-library__system-source-note" role="note">
                  <Info size={15} aria-hidden="true" />
                  <p>
                  带“原版 PDF”标识的论文可直接打开完整原文，并使用 Qwen 按全文或指定页辅助阅读；
                  其余记录用于扩大主题发现范围。
                  </p>
                </div>

              <form className="resource-library__system-search" onSubmit={submitKnowledgeSearch}>
                <label>
                  <Search size={17} aria-hidden="true" />
                  <input
                    type="search"
                    value={knowledgeQuery}
                    onChange={(event) => setKnowledgeQuery(event.target.value)}
                    placeholder="例如：绿色金融政策如何影响企业绿色技术创新"
                  />
                </label>
                <label className="resource-library__system-check">
                  <input
                    type="checkbox"
                    checked={knowledgeFulltextOnly}
                    onChange={(event) => setKnowledgeFulltextOnly(event.target.checked)}
                  />
                  只看可阅读正文
                </label>
                <button type="submit" disabled={knowledgeLoading}>
                  <Sparkles size={15} aria-hidden="true" />
                  {knowledgeLoading ? '正在检索…' : '检索论文'}
                </button>
              </form>

              {knowledgeCatalog && (
                <div className="resource-library__system-formats">
                  {Object.entries(knowledgeCatalog.source_format_counts).map(([format, count]) => (
                    <span key={format}>{sourceFormatLabel(format)} <strong>{count}</strong></span>
                  ))}
                  <small>共 {knowledgeCatalog.total_documents} 篇收录</small>
                </div>
              )}

              {knowledgeError && (
                <div className="resource-library__knowledge-error" role="alert">
                  <CloudOff size={16} aria-hidden="true" />
                  <span><strong>系统论文库未连接</strong>{knowledgeError}</span>
                </div>
              )}

              {knowledgeWarnings.length > 0 && !knowledgeError && (
                <div className="resource-library__knowledge-warning" role="note">
                  <Info size={15} aria-hidden="true" />
                  <span>{knowledgeWarnings.join('；')}</span>
                </div>
              )}

              <div className="resource-library__system-result-head">
                <p>
                  {knowledgeBundle ? (
                    <><strong>{knowledgeHits.length}</strong> 条相关正文片段 · <strong>{knowledgeBundle.graph_edges.length}</strong> 条关联线索</>
                  ) : (
                    <><strong>{(knowledgeCatalog?.matched_documents ?? 0) + showcaseDocuments.length}</strong> 篇目录记录 · <strong>{showcaseDocuments.length}</strong> 篇原版 PDF</>
                  )}
                </p>
                <small>{knowledgeBundle ? `检索问题：“${knowledgeBundle.question}”` : '默认优先展示可阅读正文'}</small>
              </div>

              {knowledgeLoading && !knowledgeCatalog ? (
                <p className="resource-library__system-empty">正在读取论文目录…</p>
              ) : showcaseDocuments.length > 0 || knowledgeHits.length > 0 || Boolean(knowledgeCatalog?.items.length) ? (
                <div className="resource-library__knowledge-list" role="list">
                  {showcaseDocuments.map((item) => {
                    const showcaseMeta = showcasePdfMetadata[item.filename]
                    const itemYear = item.publicationYear ?? showcaseMeta?.year
                    const itemJournal = item.journal ?? showcaseMeta?.journal
                    const itemLicense = item.license ?? showcaseMeta?.license
                    return (
                      <article key={item.documentId} role="listitem" className="is-original-pdf">
                        <button
                          type="button"
                          className="resource-library__knowledge-main"
                          onClick={() => onOpenReader(item.documentId)}
                        >
                          <span className="resource-library__knowledge-topline">
                            <em className="is-original">原版 PDF · AI 助读</em>
                            <small>{item.pageCount} 页 · {formatBytes(item.sizeBytes)}</small>
                          </span>
                          <strong>{item.title}</strong>
                          <span>{item.author ?? '作者信息见原文'}</span>
                          <small>{itemYear ?? '年份未知'}{itemJournal ? ` · ${itemJournal}` : ''}{item.doi ? ` · DOI ${item.doi}` : ''}{itemLicense ? ` · ${itemLicense}` : ''}</small>
                        </button>
                        <div className="resource-library__knowledge-actions">
                          <button type="button" onClick={() => onOpenReader(item.documentId)}>
                            <BookOpenCheck size={14} aria-hidden="true" />
                            阅读完整原文
                          </button>
                        </div>
                      </article>
                    )
                  })}
                  {knowledgeHits.length > 0 ? knowledgeHits.map((hit) => (
                    <article key={hit.chunk_id} role="listitem" className={selectedKnowledgeHit?.chunk_id === hit.chunk_id ? 'is-selected' : ''}>
                      <button
                        type="button"
                        className="resource-library__knowledge-main"
                        onClick={() => {
                          setSelectedKnowledgeHit(hit)
                          setSelectedKnowledgeDocument(null)
                          setDetailOpen(true)
                        }}
                      >
                        <span className="resource-library__knowledge-topline">
                          <em className={hit.evidence_status.includes('fulltext') ? 'is-fulltext' : ''}>
                            {hit.evidence_status.includes('fulltext') ? '正文片段' : '题录命中'}
                          </em>
                          <small>相似度 {(hit.retrieval_score * 100).toFixed(1)}%</small>
                        </span>
                        <strong>{hit.title}</strong>
                        <span>{hit.text}</span>
                        <small>
                          {hit.publication_year ?? '年份未知'}
                          {hit.source_locator.section ? ` · ${hit.source_locator.section}` : ''}
                          {hit.doi ? ` · DOI ${hit.doi}` : ''}
                        </small>
                      </button>
                      {hit.evidence_status.includes('fulltext') && (
                        <div className="resource-library__knowledge-actions">
                          <button type="button" onClick={() => void openKnowledgeReader(hit.document_id)}>
                            <BookOpenCheck size={14} aria-hidden="true" />
                            开始阅读
                          </button>
                        </div>
                      )}
                    </article>
                  )) : knowledgeCatalog?.items.map((document) => (
                    <article key={document.document_id} role="listitem" className={selectedKnowledgeDocument?.document_id === document.document_id ? 'is-selected' : ''}>
                      <button
                        type="button"
                        className="resource-library__knowledge-main"
                        onClick={() => {
                          setSelectedKnowledgeDocument(document)
                          setSelectedKnowledgeHit(null)
                          setDetailOpen(true)
                        }}
                      >
                        <span className="resource-library__knowledge-topline">
                          <em className={document.has_fulltext ? 'is-fulltext' : ''}>
                            {document.reading_available ? '可阅读正文' : document.has_fulltext ? '已建立索引' : '仅题录/摘要'}
                          </em>
                          <small>{sourceFormatLabel(document.source_format)}</small>
                        </span>
                        <strong>{document.title}</strong>
                        <span>{document.abstract || (document.authors.length ? document.authors.join('、') : '该记录未提供可展示摘要。')}</span>
                        <small>{document.publication_year ?? '年份未知'}{document.journal ? ` · ${document.journal}` : ''}{document.doi ? ` · DOI ${document.doi}` : ''}</small>
                      </button>
                      {document.reading_available && (
                        <div className="resource-library__knowledge-actions">
                          <button type="button" onClick={() => void openKnowledgeReader(document.document_id)}>
                            <BookOpenCheck size={14} aria-hidden="true" />
                            开始阅读
                          </button>
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              ) : !knowledgeError && (
                <p className="resource-library__system-empty">没有找到符合条件的系统论文记录。</p>
              )}

              {!knowledgeBundle && knowledgeCatalog?.next_offset !== null && knowledgeCatalog?.next_offset !== undefined && (
                <button
                  type="button"
                  className="resource-library__load-more"
                  disabled={knowledgeLoading}
                  onClick={() => void refreshKnowledgeCatalog(knowledgeCatalog.next_offset ?? 0, true)}
                >
                  加载更多
                  <span>{knowledgeCatalog.items.length} / {knowledgeCatalog.matched_documents}</span>
                </button>
              )}
            </section>
          )}

          {kind === 'literature' && literatureShelf === 'uploads' && (
            <section className="resource-library__originals" aria-labelledby="original-pdf-title">
              <div className="resource-library__originals-head">
                <div>
                  <span><FileCheck2 size={15} aria-hidden="true" />原始 PDF</span>
                  <h2 id="original-pdf-title">上传论文原文，直接开始 AI 阅读</h2>
                  <p>上传后可按页浏览、向 AI 提问，也可以随时从本机资料库删除。</p>
                </div>
                <button type="button" disabled={uploadingPdf} onClick={() => pdfInputRef.current?.click()}>
                  <Upload size={15} aria-hidden="true" />
                  {uploadingPdf ? '正在解析原文…' : '上传原始 PDF'}
                </button>
                <input ref={pdfInputRef} type="file" accept="application/pdf,.pdf" hidden onChange={(event) => void uploadOriginalPdf(event)} />
              </div>

              {pdfError && <div className="resource-library__pdf-error" role="alert"><Info size={14} />{pdfError}</div>}

              {originalDocumentsLoading ? (
                <p className="resource-library__originals-empty">正在读取原始 PDF 清单…</p>
              ) : uploadedDocuments.length > 0 ? (
                <div className="resource-library__original-list">
                  {uploadedDocuments.map((item) => (
                    <article key={item.documentId}>
                      <span className="resource-library__original-icon"><FileCheck2 size={18} /></span>
                      <div className="resource-library__original-copy">
                        <strong>{item.title}</strong>
                        <span title={item.filename}>{item.filename}</span>
                        <small>{item.pageCount} 页 · {formatBytes(item.sizeBytes)} · SHA-256 {item.sha256.slice(0, 12)}…</small>
                      </div>
                      <div className="resource-library__original-actions">
                        <button type="button" onClick={() => onOpenReader(item.documentId)}>
                          AI 读原文<ChevronRight size={14} />
                        </button>
                        <button
                          type="button"
                          className="is-delete"
                          aria-label={`删除原始 PDF：${item.title}`}
                          onClick={() => setPendingPdfDelete(item)}
                        >
                          <Trash2 size={14} aria-hidden="true" />删除
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="resource-library__originals-empty">还没有上传原始 PDF。上传后，原文件会出现在这里。</p>
              )}
            </section>
          )}

          {showFixtureResults && <>
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
                  const policyDocument = POLICY_DOCUMENTS[resource.id]
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
                            {policyDocument && (
                              <span className="resource-library__reader-ready">
                                <FileText size={12} aria-hidden="true" />完整原文
                              </span>
                            )}
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
                      <div className="resource-library__card-actions">
                        {policyDocument && (
                          <button
                            type="button"
                            className="resource-library__read"
                            onClick={() => {
                              setSelectedResourceId(resource.id)
                              setDetailOpen(true)
                              setPolicyReaderOpen(true)
                            }}
                          >
                            <FileText size={14} aria-hidden="true" />阅读原文
                          </button>
                        )}
                        <button
                          type="button"
                          className={`resource-library__quick-add ${inBasket ? 'is-added' : ''}`}
                          disabled={!effectiveProjectId}
                          aria-label={inBasket ? `从当前项目移除${resource.title}` : `将${resource.title}加入当前项目`}
                          onClick={() => toggleResource(resource)}
                        >
                          {inBasket ? <Check size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
                          {inBasket ? '已加入项目' : '加入项目'}
                        </button>
                      </div>
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
              <p>换一个关键词或减少筛选条件。当前筛选不会影响已经加入项目的资料。</p>
              <button type="button" onClick={clearFilters}>
                <FilterX size={15} aria-hidden="true" />
                重置筛选
              </button>
            </div>
          )}
          </>}
        </main>

        <aside
          className={`resource-library__detail ${detailOpen ? 'is-open' : ''}`}
          aria-label="资源详情"
          aria-hidden={!detailOpen || !(selectedResource || selectedKnowledgeHit || selectedKnowledgeDocument)}
        >
          {kind === 'literature' && literatureShelf === 'system' && (selectedKnowledgeHit || selectedKnowledgeDocument) ? (
            <>
              <div className="resource-library__detail-head">
                <span><Network size={16} aria-hidden="true" />系统论文详情</span>
                <button type="button" aria-label="关闭系统论文详情" onClick={() => setDetailOpen(false)}>
                  <X size={17} aria-hidden="true" />
                </button>
              </div>
              <div className="resource-library__detail-scroll">
                <div className="resource-library__detail-title">
                  <span className={`resource-library__availability ${(selectedKnowledgeHit?.evidence_status.includes('fulltext') || selectedKnowledgeDocument?.has_fulltext) ? 'is-ready' : 'is-limited'}`}>
                    {(selectedKnowledgeHit?.evidence_status.includes('fulltext') || selectedKnowledgeDocument?.reading_available) ? '可阅读正文' : '仅题录/摘要'}
                  </span>
                  <h2>{selectedKnowledgeHit?.title ?? selectedKnowledgeDocument?.title}</h2>
                  <p>{selectedKnowledgeHit?.text ?? selectedKnowledgeDocument?.abstract ?? '该记录未提供可展示摘要。'}</p>
                </div>

                <dl className="resource-library__facts">
                  <div>
                    <dt><Building2 size={13} aria-hidden="true" />来源</dt>
                    <dd>系统论文库</dd>
                  </div>
                  <div>
                    <dt>年份</dt>
                    <dd>{selectedKnowledgeHit?.publication_year ?? selectedKnowledgeDocument?.publication_year ?? '未知'}</dd>
                  </div>
                  <div>
                    <dt>期刊</dt>
                    <dd>{selectedKnowledgeDocument?.journal ?? '未记录'}</dd>
                  </div>
                  <div>
                    <dt>DOI</dt>
                    <dd>{selectedKnowledgeHit?.doi ?? selectedKnowledgeDocument?.doi ?? '未记录'}</dd>
                  </div>
                  {selectedKnowledgeHit && (
                    <>
                      <div><dt>检索相似度</dt><dd>{(selectedKnowledgeHit.retrieval_score * 100).toFixed(1)}%</dd></div>
                      <div><dt>片段位置</dt><dd>{selectedKnowledgeHit.source_locator.section ?? `chunk ${selectedKnowledgeHit.chunk_id}`}</dd></div>
                    </>
                  )}
                  {selectedKnowledgeDocument && (
                    <>
                      <div><dt>数据形态</dt><dd>{sourceFormatLabel(selectedKnowledgeDocument.source_format)}</dd></div>
                      <div><dt>作者</dt><dd>{selectedKnowledgeDocument.authors.join('、') || '未记录'}</dd></div>
                    </>
                  )}
                </dl>

                <div className="resource-library__boundary-note">
                  <Info size={16} aria-hidden="true" />
                  <p><strong>阅读提示</strong>系统正文适合检索和通读。需要核对论文版式、图表和原始页码时，请使用“我的原始 PDF”。</p>
                </div>
              </div>
              <div className="resource-library__detail-actions">
                {(selectedKnowledgeHit?.evidence_status.includes('fulltext') || selectedKnowledgeDocument?.reading_available) && (
                  <button
                    type="button"
                    className="resource-library__read-primary"
                    onClick={() => void openKnowledgeReader(
                      selectedKnowledgeHit?.document_id ?? selectedKnowledgeDocument?.document_id ?? '',
                    )}
                  >
                    <BookOpenCheck size={15} aria-hidden="true" />
                    阅读正文
                  </button>
                )}
                {(selectedKnowledgeHit?.doi || selectedKnowledgeDocument?.doi) ? (
                  <a
                    className="resource-library__doi-link"
                    href={`https://doi.org/${selectedKnowledgeHit?.doi ?? selectedKnowledgeDocument?.doi ?? ''}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    查看 DOI 来源<ArrowRight size={14} aria-hidden="true" />
                  </a>
                ) : (
                  <small>该记录没有可跳转 DOI；请按标题另行核对来源。</small>
                )}
              </div>
            </>
          ) : selectedResource ? (
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
                    <p><strong>数据边界</strong>加入项目只保存目录引用；未实际导入且缺少文件名、哈希和大小的条目不会进入正式任务的 datasetRefs。</p>
                  </div>
                )}
                {selectedResource.kind === 'policy' && (
                  <div className="resource-library__boundary-note">
                    {selectedPolicyDocument ? <ShieldCheck size={16} aria-hidden="true" /> : <Info size={16} aria-hidden="true" />}
                    {selectedPolicyDocument ? (
                      <p><strong>原文已核验</strong>系统已保存完整政策文本，并标注发文机关、文号、发布日期与政府官方来源。</p>
                    ) : (
                      <p><strong>确认边界</strong>政策摘要需由研究者确认，才会进入研究任务的已知政策事实。</p>
                    )}
                  </div>
                )}
                {selectedResource.kind === 'literature' && (
                  <div className="resource-library__boundary-note">
                    <Info size={16} aria-hidden="true" />
                    <p><strong>原文边界</strong>这是目录元数据，不是论文全文。只有上传到“原始 PDF”的文件才能进入 AI 原文阅读。</p>
                  </div>
                )}
              </div>
              <div className="resource-library__detail-actions">
                {selectedPolicyDocument && (
                  <button
                    type="button"
                    className="resource-library__read-primary"
                    onClick={() => setPolicyReaderOpen(true)}
                  >
                    <FileText size={15} aria-hidden="true" />
                    阅读政策原文
                  </button>
                )}
                <button
                  type="button"
                  className={selectedIsInBasket ? 'is-added' : ''}
                  disabled={!effectiveProjectId}
                  onClick={() => toggleResource(selectedResource)}
                >
                  {selectedIsInBasket ? <Check size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
                  {selectedIsInBasket ? '已加入当前项目' : '加入当前项目'}
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

      {policyReaderOpen && selectedPolicyDocument && (
        <div className="resource-library__modal-scrim" role="presentation" onMouseDown={() => setPolicyReaderOpen(false)}>
          <section
            className="resource-library__text-reader resource-library__policy-reader"
            role="dialog"
            aria-modal="true"
            aria-labelledby="policy-reader-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span><FileText size={15} aria-hidden="true" />政策原文</span>
                <h2 id="policy-reader-title">{selectedPolicyDocument.title}</h2>
                <small>
                  {selectedPolicyDocument.documentNumber} · {selectedPolicyDocument.issueDate}
                </small>
              </div>
              <button type="button" aria-label="关闭政策原文" onClick={() => setPolicyReaderOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>

            <div className="resource-library__text-reader-note">
              <ShieldCheck size={14} aria-hidden="true" />
              <span>完整文本已预置，可离线演示；文号、发文机关和正文均可从官方来源核对。</span>
              <a href={selectedPolicyDocument.sourceUrl} target="_blank" rel="noreferrer">
                打开官方来源<ArrowRight size={13} aria-hidden="true" />
              </a>
            </div>

            <div className="resource-library__text-reader-body resource-library__policy-reader-body">
              <article>
                <div className="resource-library__policy-meta">
                  <strong>{selectedPolicyDocument.documentNumber}</strong>
                  <span>发文机关：{selectedPolicyDocument.issuedBy}</span>
                  <span>发布日期：{selectedPolicyDocument.issueDate}</span>
                </div>
                <div className="resource-library__policy-lead">
                  {selectedPolicyDocument.lead.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                </div>
                {selectedPolicyDocument.sections.map((section) => (
                  <section key={section.heading}>
                    <h3>{section.heading}</h3>
                    {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                  </section>
                ))}
              </article>
            </div>

            <footer>
              <span>
                完整政策文本 · {selectedPolicyDocument.sections.length} 个章节 · {' '}
                {selectedPolicyDocument.sections.reduce((total, section) => total + section.paragraphs.length, selectedPolicyDocument.lead.length)} 个正文段落
              </span>
              <a href={selectedPolicyDocument.sourceUrl} target="_blank" rel="noreferrer">
                {selectedPolicyDocument.sourceLabel}<ArrowRight size={13} aria-hidden="true" />
              </a>
            </footer>
          </section>
        </div>
      )}

      {knowledgeReaderOpen && (
        <div className="resource-library__modal-scrim" role="presentation" onMouseDown={() => setKnowledgeReaderOpen(false)}>
          <section
            className="resource-library__text-reader"
            role="dialog"
            aria-modal="true"
            aria-labelledby="knowledge-reader-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span><BookOpenCheck size={15} aria-hidden="true" />系统论文阅读</span>
                <h2 id="knowledge-reader-title">{knowledgeReader?.title ?? '正在打开论文…'}</h2>
                {knowledgeReader && (
                  <small>
                    {sourceFormatLabel(knowledgeReader.source_format)} · {knowledgeReader.total_characters.toLocaleString('zh-CN')} 字符
                  </small>
                )}
              </div>
              <button type="button" aria-label="关闭论文阅读" onClick={() => setKnowledgeReaderOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>

            <div className="resource-library__text-reader-note">
              <Info size={14} aria-hidden="true" />
              <span>这里展示论文库中的可阅读正文；原始版式、图表和页码请以 PDF 为准。</span>
            </div>

            <div className="resource-library__text-reader-body">
              {knowledgeReaderError && <p className="is-error" role="alert">{knowledgeReaderError}</p>}
              {!knowledgeReader && knowledgeReaderLoading ? (
                <p className="is-loading">正在载入论文正文…</p>
              ) : knowledgeReader ? (
                <pre>{knowledgeReader.text}</pre>
              ) : !knowledgeReaderError && (
                <p className="is-loading">这篇论文暂时没有可阅读正文。</p>
              )}
            </div>

            {knowledgeReader && (
              <footer>
                <span>已载入 {knowledgeReader.text.length.toLocaleString('zh-CN')} / {knowledgeReader.total_characters.toLocaleString('zh-CN')} 字符</span>
                {knowledgeReader.next_offset ? (
                  <button type="button" disabled={knowledgeReaderLoading} onClick={() => void loadMoreKnowledgeText()}>
                    {knowledgeReaderLoading ? '正在载入…' : '继续阅读'}
                  </button>
                ) : (
                  <small>已到正文末尾</small>
                )}
              </footer>
            )}
          </section>
        </div>
      )}

      {pendingPdfDelete && (
        <div className="resource-library__modal-scrim" role="presentation" onMouseDown={() => setPendingPdfDelete(null)}>
          <section
            className="resource-library__delete-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-pdf-title"
            aria-describedby="delete-pdf-description"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <span className="resource-library__delete-dialog-icon"><Trash2 size={20} aria-hidden="true" /></span>
            <h2 id="delete-pdf-title">删除这篇原始 PDF？</h2>
            <p id="delete-pdf-description">
              “{pendingPdfDelete.title}”的原文件和逐页文本将从本机资料库删除，此操作无法撤销。
            </p>
            <div>
              <button type="button" disabled={Boolean(deletingPdfId)} onClick={() => setPendingPdfDelete(null)}>取消</button>
              <button type="button" className="is-danger" disabled={Boolean(deletingPdfId)} onClick={() => void deleteOriginalPdf()}>
                <Trash2 size={14} aria-hidden="true" />
                {deletingPdfId ? '正在删除…' : '确认删除'}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  )
}
