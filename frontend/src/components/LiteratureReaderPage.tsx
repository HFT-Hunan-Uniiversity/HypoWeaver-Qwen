import {
  ArrowLeft,
  BookOpenCheck,
  BookmarkPlus,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  Clipboard,
  Download,
  ExternalLink,
  FileCheck2,
  FileSearch,
  Hash,
  MessageSquareText,
  Send,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { workflowApi } from '../runtime/api'
import type { OriginalLiteratureDocument } from '../runtime/types'
import '../reader.css'

interface ReaderMessage {
  id: string
  role: 'assistant' | 'user'
  content: string
  source?: string
  error?: boolean
}

const QUICK_QUESTIONS = [
  '概括这份原文的核心问题和结论',
  '作者使用了什么研究方法？',
  '梳理原文中的数据、变量与样本',
  '原文有哪些局限或研究空白？',
]

const bundledPaperMetadata: Record<string, { year: number; journal: string; doi: string; license: string }> = {
  'green-finance-environmental-violations-jfr.pdf': { year: 2024, journal: '金融研究', doi: '', license: '期刊官网公开全文' },
  'corporate-green-bonds-jfe.pdf': { year: 2021, journal: 'Journal of Financial Economics', doi: '10.1016/j.jfineco.2021.01.010', license: '作者公开全文' },
  'carbon-risk-jfe.pdf': { year: 2021, journal: 'Journal of Financial Economics', doi: '10.1016/j.jfineco.2021.05.008', license: 'NBER 公开工作论文' },
  'green-finance-air-quality.pdf': { year: 2023, journal: 'Sustainability', doi: '10.3390/su15054068', license: 'CC BY 4.0' },
  'green-finance-green-innovation.pdf': { year: 2022, journal: 'International Journal of Environmental Research and Public Health', doi: '10.3390/ijerph19127330', license: 'CC BY 4.0' },
  'green-finance-enterprise-technology.pdf': { year: 2022, journal: 'Sustainability', doi: '10.3390/su14169865', license: 'CC BY 4.0' },
}

function isBundledShowcase(document: OriginalLiteratureDocument): boolean {
  return Boolean(document.isShowcase || bundledPaperMetadata[document.filename])
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '读取原始 PDF 时发生未知错误。'
}

function renderInlineMarkdown(value: string): ReactNode[] {
  return value.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => (
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
      : <span key={`${part}-${index}`}>{part}</span>
  ))
}

function ReaderMessageText({ content }: { content: string }) {
  return <div className="paper-reader__message-rich">{content.split('\n').map((line, index) => {
    const trimmed = line.trim()
    if (!trimmed) return <span className="paper-reader__message-space" key={`space-${index}`} />
    const bullet = trimmed.match(/^\*\s+(.*)$/)
    return <p className={bullet ? 'is-bullet' : undefined} key={`${trimmed}-${index}`}>
      {bullet && <span aria-hidden="true">•</span>}
      <span>{renderInlineMarkdown(bullet?.[1] ?? trimmed)}</span>
    </p>
  })}</div>
}

export interface LiteratureReaderPageProps {
  resourceId: string
  activeProjectId: string | null
  onBack: () => void
}

export function LiteratureReaderPage({ resourceId, activeProjectId, onBack }: LiteratureReaderPageProps) {
  const [document, setDocument] = useState<OriginalLiteratureDocument | null>(null)
  const [pdfUrl, setPdfUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [scope, setScope] = useState<'document' | 'page'>('document')
  const [assistantTab, setAssistantTab] = useState<'assistant' | 'notes'>('assistant')
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [messages, setMessages] = useState<ReaderMessage[]>([])
  const [notes, setNotes] = useState('')
  const [notesSaved, setNotesSaved] = useState(false)
  const [evidencePages, setEvidencePages] = useState<number[]>([])
  const [copied, setCopied] = useState(false)
  const documentViewportRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false
    let objectUrl = ''
    setLoading(true)
    setLoadError('')
    Promise.all([
      workflowApi.getLiteratureDocument(resourceId),
      workflowApi.getLiteraturePdf(resourceId),
    ]).then(([nextDocument, blob]) => {
      if (cancelled) return
      objectUrl = URL.createObjectURL(blob)
      setDocument(nextDocument)
      setPdfUrl(objectUrl)
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: isBundledShowcase(nextDocument)
          ? '这是一篇已预置的公开可访问原版论文。我可以基于整篇原文或当前页实时阅读，并在回答中标注对应页码，方便你与中间的 PDF 页面逐项核对。'
          : '我会读取这份 PDF 的原始文本层回答问题。回答会标注原始页码，方便你回到中间的论文页面核对。',
        source: `${nextDocument.pageCount} 页 · PDF SHA-256 ${nextDocument.sha256.slice(0, 12)}…`,
      }])
      setNotes(window.localStorage.getItem(`hypoweaver.literature-notes.${resourceId}`) ?? '')
    }).catch((error) => {
      if (!cancelled) setLoadError(errorMessage(error))
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [resourceId])

  const currentPageSummary = useMemo(
    () => document?.pages.find((page) => page.pageNumber === currentPage),
    [currentPage, document],
  )
  const bundledMetadata = document ? bundledPaperMetadata[document.filename] : undefined
  const publicationYear = document?.publicationYear ?? bundledMetadata?.year
  const journal = document?.journal ?? bundledMetadata?.journal
  const doi = document?.doi ?? bundledMetadata?.doi
  const sourceUrl = document?.sourceUrl ?? (doi ? `https://doi.org/${doi}` : undefined)
  const license = document?.license ?? bundledMetadata?.license

  useEffect(() => {
    const viewport = documentViewportRef.current
    if (!viewport || !document) return
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0]
      const pageNumber = Number((visible?.target as HTMLElement | undefined)?.dataset.page)
      if (Number.isInteger(pageNumber) && pageNumber > 0) setCurrentPage(pageNumber)
    }, { root: viewport, threshold: [0.25, 0.55, 0.8] })
    viewport.querySelectorAll<HTMLElement>('[data-page]').forEach((page) => observer.observe(page))
    return () => observer.disconnect()
  }, [document])

  async function ask(value: string) {
    const prompt = value.trim()
    if (!prompt || !document || asking) return
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', content: prompt }])
    setQuestion('')
    setAsking(true)
    try {
      const response = await workflowApi.askLiterature(document.documentId, {
        question: prompt,
        ...(scope === 'page' ? { pageNumbers: [currentPage] } : {}),
      })
      const locatedPages = response.citedPages.length ? response.citedPages : response.usedPages
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.answer,
        source: `${response.model} · ${locatedPages.map((page) => `原文第 ${page} 页`).join('、')} · ${response.usedCharacters.toLocaleString('zh-CN')} 字符`,
      }])
    } catch (error) {
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: errorMessage(error),
        source: '请求失败，未生成演示答案或加工文本作为替代。',
        error: true,
      }])
    } finally {
      setAsking(false)
    }
  }

  function submitQuestion(event: FormEvent) {
    event.preventDefault()
    void ask(question)
  }

  function movePage(next: number) {
    if (!document || Number.isNaN(next)) return
    const pageNumber = Math.min(document.pageCount, Math.max(1, next))
    setCurrentPage(pageNumber)
    globalThis.document.getElementById(`paper-reader-page-${pageNumber}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function toggleEvidencePage() {
    setEvidencePages((current) => current.includes(currentPage)
      ? current.filter((page) => page !== currentPage)
      : [...current, currentPage].sort((left, right) => left - right))
  }

  function saveNotes() {
    window.localStorage.setItem(`hypoweaver.literature-notes.${resourceId}`, notes)
    setNotesSaved(true)
  }

  async function copySourceIdentity() {
    if (!document) return
    try {
      await navigator.clipboard.writeText(
        `${document.title}\n原始文件：${document.filename}\nPDF SHA-256：${document.sha256}`,
      )
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  if (loading) {
    return (
      <section className="paper-reader paper-reader--empty">
        <FileSearch size={30} aria-hidden="true" />
        <h1>正在校验原始 PDF</h1>
        <p>正在读取文档清单、PDF 哈希和原始文件。</p>
      </section>
    )
  }

  if (!document || !pdfUrl || loadError) {
    return (
      <section className="paper-reader paper-reader--empty">
        <FileSearch size={30} aria-hidden="true" />
        <h1>无法打开这份原始 PDF</h1>
        <p>{loadError || '文档记录或原始文件不存在。'}</p>
        <button type="button" onClick={onBack}><ArrowLeft size={15} />返回文献库</button>
      </section>
    )
  }

  return (
    <section className="paper-reader" aria-labelledby="paper-reader-title">
      <header className="paper-reader__header">
        <button type="button" className="paper-reader__back" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" />文献库
        </button>
        <div className="paper-reader__header-copy">
          <span><BookOpenCheck size={14} aria-hidden="true" />Qwen · 原版论文阅读</span>
          <strong id="paper-reader-title">{document.title}</strong>
        </div>
        <div className="paper-reader__header-actions">
          <button type="button" className="paper-reader__mobile-ai" onClick={() => globalThis.document.getElementById('paper-reader-assistant')?.scrollIntoView({ behavior: 'smooth' })}>
            <Bot size={14} />AI 助读
          </button>
          <button type="button" onClick={() => void copySourceIdentity()}>
            {copied ? <Check size={14} /> : <Clipboard size={14} />}{copied ? '已复制' : '复制来源'}
          </button>
          {sourceUrl && (
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />期刊来源
            </a>
          )}
          <a href={pdfUrl} download={document.filename}><Download size={14} />下载原始 PDF</a>
        </div>
      </header>

      <div className="paper-reader__layout">
        <aside className="paper-reader__outline" aria-label="原始 PDF 信息与翻页">
          <div className="paper-reader__foundation">
            <span><ShieldCheck size={14} aria-hidden="true" />{isBundledShowcase(document) ? '公开可访问原版已校验' : '原始文件已校验'}</span>
            <strong>{document.pageCount} 页 · {formatBytes(document.sizeBytes)}</strong>
            <small>AI 读取服务端保存的同一份 PDF 文本层</small>
          </div>

          <section className="paper-reader__source-card">
            <p>原始文件</p>
            <strong title={document.filename}>{document.filename}</strong>
            {document.author && <span>{document.author}</span>}
            {(publicationYear || journal) && <span>{publicationYear ?? '年份未知'} · {journal ?? '期刊未记录'}</span>}
            {doi && <span>DOI {doi}</span>}
            {license && <span>{license}</span>}
            <span><Hash size={11} />{document.sha256.slice(0, 16)}…</span>
            <span><FileCheck2 size={11} />{document.extractedPageCount}/{document.pageCount} 页含文本</span>
          </section>

          <nav className="paper-reader__page-nav" aria-label="PDF 翻页">
            <p>页码</p>
            <div>
              <button type="button" disabled={currentPage <= 1} onClick={() => movePage(currentPage - 1)} aria-label="上一页"><ChevronLeft size={15} /></button>
              <label><span className="sr-only">当前页</span><input type="number" min={1} max={document.pageCount} value={currentPage} onChange={(event) => movePage(Number(event.target.value))} /></label>
              <span>/ {document.pageCount}</span>
              <button type="button" disabled={currentPage >= document.pageCount} onClick={() => movePage(currentPage + 1)} aria-label="下一页"><ChevronRight size={15} /></button>
            </div>
            <small>{currentPageSummary?.characterCount.toLocaleString('zh-CN') ?? 0} 个原文字符</small>
            <small>页文本哈希 {currentPageSummary?.textSha256.slice(0, 12) ?? '—'}…</small>
          </nav>

          <button type="button" className={`paper-reader__evidence-page ${evidencePages.includes(currentPage) ? 'is-selected' : ''}`} onClick={toggleEvidencePage}>
            {evidencePages.includes(currentPage) ? <Check size={14} /> : <BookmarkPlus size={14} />}
            {evidencePages.includes(currentPage) ? `已标记原文第 ${currentPage} 页` : `标记原文第 ${currentPage} 页`}
          </button>

          <div className="paper-reader__boundary">
            <strong>读取边界</strong>
            <p>当前只抽取 PDF 自带文本层。扫描图片、公式布局与图表视觉含义不会被假装成可读文本。</p>
          </div>
        </aside>

        <main className="paper-reader__document" aria-label="原始 PDF 阅读器">
          <div className="paper-reader__pdf-status">
            <span><FileCheck2 size={14} />完整原版 PDF · 连续阅读</span>
            <small>共 {document.pageCount} 页 · 可滚动、缩放、搜索和打印</small>
          </div>
          <div ref={documentViewportRef} className="paper-reader__page-stack" aria-label={`${document.title} 完整原版 PDF，共 ${document.pageCount} 页`}>
            {document.pages.map((page) => (
              <figure id={`paper-reader-page-${page.pageNumber}`} data-page={page.pageNumber} className="paper-reader__pdf-page" key={page.pageNumber}>
                <img
                  src={`/api/v1/literature/documents/${encodeURIComponent(document.documentId)}/pages/${page.pageNumber}/image`}
                  alt={`${document.filename} 原文第 ${page.pageNumber} 页`}
                  loading={page.pageNumber <= 2 ? 'eager' : 'lazy'}
                  decoding="async"
                />
                <figcaption>原文第 {page.pageNumber} 页 / 共 {document.pageCount} 页</figcaption>
              </figure>
            ))}
          </div>
        </main>

        <aside id="paper-reader-assistant" className="paper-reader__assistant" aria-label="AI 原文阅读">
          <div className="paper-reader__assistant-head">
            <div>
              <span><Bot size={15} aria-hidden="true" />AI 原文阅读</span>
              <small>Qwen 只接收服务端校验过的原文页</small>
            </div>
            <span className={`paper-reader__online ${asking ? 'is-busy' : ''}`}><span />{asking ? '阅读中' : '就绪'}</span>
          </div>

          <div className="paper-reader__assistant-tabs" role="tablist" aria-label="阅读辅助工具">
            <button type="button" role="tab" aria-selected={assistantTab === 'assistant'} className={assistantTab === 'assistant' ? 'is-active' : ''} onClick={() => setAssistantTab('assistant')}><MessageSquareText size={14} />AI 助读</button>
            <button type="button" role="tab" aria-selected={assistantTab === 'notes'} className={assistantTab === 'notes' ? 'is-active' : ''} onClick={() => setAssistantTab('notes')}><BookmarkPlus size={14} />笔记与页码{evidencePages.length > 0 && <span>{evidencePages.length}</span>}</button>
          </div>

          {assistantTab === 'assistant' ? (
            <>
              <div className="paper-reader__scope" aria-label="AI 阅读范围">
                <button type="button" className={scope === 'document' ? 'is-active' : ''} onClick={() => setScope('document')}>整份原文</button>
                <button type="button" className={scope === 'page' ? 'is-active' : ''} onClick={() => setScope('page')}>仅第 {currentPage} 页</button>
              </div>
              <div className="paper-reader__messages" aria-live="polite">
                {messages.map((message) => (
                  <div className={`paper-reader__message is-${message.role} ${message.error ? 'is-error' : ''}`} key={message.id}>
                    <span>{message.role === 'assistant' ? <Bot size={14} /> : '你'}</span>
                    <div><ReaderMessageText content={message.content} />{message.source && <small><FileSearch size={11} />{message.source}</small>}</div>
                  </div>
                ))}
                {asking && <div className="paper-reader__message is-assistant is-thinking"><span><Bot size={14} /></span><div><p>正在核对原始 PDF 文本层并生成页码引用…</p></div></div>}
              </div>
              <div className="paper-reader__quick-questions">
                {QUICK_QUESTIONS.map((item) => <button type="button" key={item} disabled={asking} onClick={() => void ask(item)}>{item}</button>)}
              </div>
              <form className="paper-reader__ask" onSubmit={submitQuestion}>
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="向 AI 询问这份原始 PDF…" aria-label="向 AI 询问原始 PDF" />
                <button type="submit" disabled={!question.trim() || asking} aria-label="发送问题"><Send size={15} /></button>
              </form>
            </>
          ) : (
            <div className="paper-reader__notes">
              <section>
                <span><BookmarkPlus size={14} />已标记原文页</span>
                {evidencePages.length > 0 ? <ul>{evidencePages.map((page) => <li key={page}>原文第 {page} 页</li>)}</ul> : <p>在左侧标记需要复核或后续引用的原文页。</p>}
              </section>
              <label><span>阅读笔记</span><textarea value={notes} onChange={(event) => { setNotes(event.target.value); setNotesSaved(false) }} placeholder="记录原文中的关键发现、问题和待核实事项…" /></label>
              <button type="button" disabled={!notes.trim()} onClick={saveNotes}>{notesSaved ? <Check size={14} /> : <BookmarkPlus size={14} />}{notesSaved ? '笔记已保存' : '保存本地笔记'}</button>
              <small>{activeProjectId ? '笔记已保存在本机；与当前项目 EvidenceBundle 的正式关联仍待接入。' : '笔记只保存在本机浏览器中。'}</small>
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}
