import { useState } from 'react'
export interface Evidence {
  id: string
  title: string
  year: number | null
  abstract: string
  fulltext_excerpt: string
  included: boolean
  doi: string | null
}
export default function EvidenceChip({ card }: { card: Evidence }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        className="evidence-chip secondary"
        title={card.abstract || card.fulltext_excerpt || '暂无摘要'}
        onClick={() => setOpen(true)}
      >
        {card.title} {card.year && `（${card.year}）`}
      </button>
      {open && (
        <div className="modal-backdrop">
          <section className="modal" role="dialog" aria-modal="true" aria-label="文献证据">
            <h2>{card.title}</h2>
            <p>
              {card.year} · {card.included ? '已纳入' : '已排除'}
            </p>
            <p className="prewrap">
              {card.abstract || card.fulltext_excerpt || '此来源未提供摘要或正文摘录。'}
            </p>
            {card.doi && (
              <p>
                <a href={`https://doi.org/${card.doi}`} target="_blank" rel="noreferrer">
                  打开 DOI
                </a>
              </p>
            )}
            <button onClick={() => setOpen(false)}>关闭</button>
          </section>
        </div>
      )}
    </>
  )
}
