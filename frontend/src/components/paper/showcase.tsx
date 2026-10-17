import { Check, ChevronDown } from 'lucide-react'
import {
  SHOWCASE_PAPER,
  SHOWCASE_PAPER_FIGURES,
  SHOWCASE_PAPER_TABLES,
  SHOWCASE_TEN,
  SHOWCASE_TEN_STATUS,
  type ShowcasePaperBlock,
  type ShowcasePaperFigure,
  type ShowcasePaperTable,
} from '../../data/showcaseResearch'
import type { PaperData, PaperSection } from './PaperView'

function Figure({ figure }: { figure: ShowcasePaperFigure }) {
  return (
    <figure className="hw-paper__figure">
      <img src={figure.src} data-word-src={figure.wordSrc} alt={figure.alt} loading="lazy" />
      <figcaption>
        <strong>{figure.title}</strong>
        <span>{figure.note}</span>
      </figcaption>
    </figure>
  )
}

function Table({ table }: { table: ShowcasePaperTable }) {
  return (
    <figure className="hw-paper__table">
      <figcaption>{table.title}</figcaption>
      <div className="hw-paper__table-wrap">
        <table>
          <thead>
            <tr>
              {table.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, c) => (
                  <td key={c}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>{table.note}</p>
    </figure>
  )
}

function Block({ block }: { block: ShowcasePaperBlock }) {
  switch (block.kind) {
    case 'paragraph':
      return <p>{block.text}</p>
    case 'subheading':
      return <h5>{block.text}</h5>
    case 'hypothesis':
      return (
        <div className="hw-paper__hypothesis">
          <strong>{block.label}</strong>
          <p>{block.text}</p>
        </div>
      )
    case 'equation':
      return (
        <div className="hw-paper__equation">
          <div>
            <span>{block.formula}</span>
            <b>{block.label}</b>
          </div>
          {block.note && <p>{block.note}</p>}
        </div>
      )
    case 'figure': {
      const f = SHOWCASE_PAPER_FIGURES.find((x) => x.id === block.id)
      return f ? <Figure figure={f} /> : null
    }
    case 'table': {
      const t = SHOWCASE_PAPER_TABLES.find((x) => x.id === block.id)
      return t ? <Table table={t} /> : null
    }
  }
}

/** 碳市场展示稿：旧版 SHOWCASE_PAPER 全文 */
export const showcaseHead: Omit<PaperData, 'sections'> = {
  kicker: '期刊规范化初稿 · 真实估计',
  title: SHOWCASE_PAPER.title,
  authors: SHOWCASE_PAPER.authors.join('，'),
  affiliation: SHOWCASE_PAPER.affiliation,
  subtitle: SHOWCASE_PAPER.subtitle,
  abstract: SHOWCASE_PAPER.abstract,
  keywords: [...SHOWCASE_PAPER.keywords],
  jel: [...SHOWCASE_PAPER.jel],
  references: SHOWCASE_PAPER.references.map((r) => r.replace(/([*_`\\[\]])/g, '\\$1')),
  dataStatement: SHOWCASE_PAPER.dataStatement.replace(/^数据与复现声明[:：]\s*/, ''),
  fileName: '碳市场与企业高质量绿色创新_公开数据复现初稿',
}

export const showcaseSections: PaperSection[] = SHOWCASE_PAPER.sections.map((s) => ({
  id: s.id,
  title: s.title,
  body: (
    <>
      <h4>{s.title}</h4>
      {(s.blocks as readonly ShowcasePaperBlock[]).map((b, i) => (
        <Block key={i} block={b} />
      ))}
    </>
  ),
}))

/** 碳市场展示版《科学十项》：按旧版成果页「科学十项」面板 1:1 复刻（只读） */
export function ShowcaseTen() {
  const confirmed = SHOWCASE_TEN.filter((x) => x.confirmed).length
  return (
    <div className="project-outcomes__panel outcome-scientific" aria-label="科学十项（展示版本）">
      <header className="outcome-panel__header is-compact">
        <div>
          <span className="outcome-kicker">
            <Check size={12} aria-hidden="true" />
            {SHOWCASE_TEN_STATUS === 'confirmed' ? '10/10 已确认' : `${confirmed}/10 已核对`}
          </span>
          <h3>科学十项研究方案</h3>
          <p>把研究构想编译为可以审查、执行和复现的完整方案。</p>
        </div>
        <span className="outcome-demo-note">展示版本 · 只读</span>
      </header>
      <div className="outcome-scientific__list">
        {SHOWCASE_TEN.map((item, index) => (
          <details key={item.itemNo} id={'ten-' + item.itemNo} open={index < 2 ? true : undefined}>
            <summary>
              <span className="outcome-scientific__number">
                {item.confirmed ? <Check size={13} /> : item.itemNo}
              </span>
              <span>
                <strong>{item.title}</strong>
                <small>
                  {item.status === 'evidence_bound'
                    ? '证据已绑定'
                    : item.status === 'conditional'
                      ? '条件性结论'
                      : '等待补充'}
                </small>
              </span>
              <ChevronDown size={15} aria-hidden="true" />
            </summary>
            <div className="outcome-scientific__content">
              <p>{item.content}</p>
              <span>证据引用：{item.evidenceRefs.join(' · ') || '待补充'}</span>
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}
