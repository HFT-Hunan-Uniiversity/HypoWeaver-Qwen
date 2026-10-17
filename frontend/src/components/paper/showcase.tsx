import {
  SHOWCASE_PAPER,
  SHOWCASE_PAPER_FIGURES,
  SHOWCASE_PAPER_TABLES,
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
