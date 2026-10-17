import { useRef, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Download, Printer } from 'lucide-react'
import '../../styles/paper.css'

export type PaperSection = { id: string; title: string; body: ReactNode; extra?: ReactNode }
export type PaperData = {
  kicker?: string
  title: string
  authors?: string
  affiliation?: string
  subtitle?: string
  /** 摘要 markdown；缺省则不显示摘要框 */
  abstract?: string
  keywords?: string[]
  /** JEL 分类号 */
  jel?: string[]
  sections: PaperSection[]
  /** 参考文献 markdown 行（不含列表符号） */
  references?: string[]
  dataStatement?: string
  fileName?: string
}

const md = (text: string) => <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>

function escapeHtml(v: string) {
  return v
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

const WORD_CSS = `body{font-family:"SimSun","Songti SC",serif;font-size:10.5pt;line-height:1.75;color:#111;margin:2.35cm 2.5cm;background:#fff}
h1{font-family:"SimHei",sans-serif;font-size:20pt;text-align:center;line-height:1.45;margin:0 0 12pt}
.hw-paper__authors,.hw-paper__affiliation,.hw-paper__subtitle{text-align:center;text-indent:0}.hw-paper__affiliation,.hw-paper__subtitle{font-size:9.5pt;color:#555}
h2,h4{font-family:"SimHei",sans-serif;font-size:14pt;text-align:center;margin:22pt 0 10pt}
h3,h5{font-family:"SimHei",sans-serif;font-size:11pt;margin:14pt 0 4pt}
p{text-indent:2em;margin:5pt 0;text-align:justify}
.hw-paper__abstract p,.hw-paper__keywords{text-indent:0}
table{width:100%;border-collapse:collapse;border-top:1.2pt solid #111;border-bottom:1.2pt solid #111;font-size:9pt}th{border-bottom:.6pt solid #111;padding:5pt 3pt;font-weight:normal}td{padding:4pt 3pt;text-align:center}
.hw-paper__references p{text-indent:-2em;padding-left:2em;font-size:9.5pt}
.hw-paper__hypothesis{margin:10pt 2em;border-left:2pt solid #333;padding:6pt 10pt}.hw-paper__hypothesis p{display:inline;text-indent:0}
.hw-paper__equation>div{text-align:center;font-family:"Times New Roman",serif;font-size:11pt;font-style:italic;margin:12pt 0}.hw-paper__equation b{float:right;font-style:normal;font-weight:normal}.hw-paper__equation>p{text-indent:0;font-size:9.5pt}
figure{margin:16pt 0;page-break-inside:avoid}figcaption{text-align:center;font-weight:bold;margin:5pt 0}figure img{display:block;max-width:100%;margin:0 auto}figure figcaption span,figure>p{display:block;font-size:8.5pt;font-weight:normal;text-align:left;text-indent:0}
.hw-paper__data{margin-top:24pt;padding-top:10pt;border-top:.6pt solid #777;color:#444;font-size:9pt}`

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = () => reject(r.error)
    r.readAsDataURL(blob)
  })
}

/** 以页面上已渲染的论文为准导出 Word（.doc，HTML 内核，Word/WPS 可直接打开）。图片内嵌为 PNG。 */
async function downloadWord(root: HTMLElement | null, data: PaperData) {
  if (!root) return
  const clone = root.cloneNode(true) as HTMLElement
  clone
    .querySelectorAll('.no-print, .hw-paper__actions, .hw-paper__toc, button, textarea, svg, canvas')
    .forEach((n) => n.remove())
  await Promise.all(
    Array.from(clone.querySelectorAll('img')).map(async (img) => {
      const src = img.getAttribute('data-word-src') || img.getAttribute('src') || ''
      try {
        const r = await fetch(src)
        if (!r.ok) throw new Error(String(r.status))
        img.setAttribute('src', await blobToDataUrl(await r.blob()))
      } catch {
        img.setAttribute('src', new URL(src, location.href).href)
      }
      img.removeAttribute('loading')
    }),
  )
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(data.title)}</title><style>${WORD_CSS}</style></head><body>${clone.innerHTML}</body></html>`
  const blob = new Blob(['\ufeff', html], { type: 'application/msword;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (data.fileName || data.title).replace(/[\\/:*?"<>|]/g, '_') + '.doc'
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

function jump(id: string) {
  document.getElementById(id)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}

export default function PaperView({
  data: head,
  sections,
  toolbar,
}: {
  data: Omit<PaperData, 'sections'>
  sections: PaperSection[]
  toolbar?: ReactNode
}) {
  const data: PaperData = { ...head, sections }
  const ref = useRef<HTMLElement>(null)
  const refs = data.references || []
  return (
    <article className="hw-paper" ref={ref}>
      <header className="hw-paper__head">
        {data.kicker && <span className="hw-paper__kicker no-print">{data.kicker}</span>}
        {data.kicker && <br className="no-print" />}
        <h1>{data.title}</h1>
        {data.authors && <p className="hw-paper__authors">{data.authors}</p>}
        {data.affiliation && <p className="hw-paper__affiliation">{data.affiliation}</p>}
        {data.subtitle && <p className="hw-paper__subtitle">{data.subtitle}</p>}
        <div className="hw-paper__actions no-print">
          <button type="button" className="product-button" onClick={() => void downloadWord(ref.current, data)}>
            <Download size={14} aria-hidden="true" /> 下载 Word
          </button>
          <button type="button" className="product-button" onClick={() => window.print()}>
            <Printer size={14} aria-hidden="true" /> 打印 / 存为 PDF
          </button>
          {toolbar}
        </div>
      </header>
      <div className="hw-paper__layout">
        <nav className="hw-paper__toc no-print" aria-label="论文目录">
          <strong>正文目录</strong>
          {data.abstract && <button type="button" onClick={() => jump('paper-abstract')}>摘要</button>}
          {data.sections.map((s) => (
            <button type="button" key={s.id} onClick={() => jump('paper-' + s.id)}>
              {s.title}
            </button>
          ))}
          {refs.length > 0 && <button type="button" onClick={() => jump('paper-references')}>参考文献</button>}
        </nav>
        <div className="hw-paper__article">
          {data.abstract && (
            <section id="paper-abstract" className="hw-paper__abstract">
              <h4>内容摘要</h4>
              {md(data.abstract)}
              {!!data.keywords?.length && (
                <p className="hw-paper__keywords">
                  <strong>关键词：</strong>
                  {data.keywords.join('；')}
                </p>
              )}
              {!!data.jel?.length && (
                <p className="hw-paper__keywords">
                  <strong>JEL分类号：</strong>
                  {data.jel.join('、')}
                </p>
              )}
            </section>
          )}
          {data.sections.map((s) => (
            <section id={'paper-' + s.id} key={s.id} className="hw-paper__section">
              {s.body}
              {s.extra}
            </section>
          ))}
          {refs.length > 0 && (
            <section id="paper-references" className="hw-paper__references">
              <h4>参考文献</h4>
              {refs.map((r, i) => (
                <div key={i} className="hw-paper__ref">
                  {md(`［${i + 1}］${r}`)}
                </div>
              ))}
            </section>
          )}
          {data.dataStatement && (
            <aside className="hw-paper__data">
              <strong>数据声明：</strong>
              {data.dataStatement}
            </aside>
          )}
        </div>
      </div>
    </article>
  )
}
