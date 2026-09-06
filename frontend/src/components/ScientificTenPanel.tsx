import {
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  ClipboardList,
  FileWarning,
  Sparkles,
} from 'lucide-react'
import { frontendDataSource, type Project, type ScientificTenItemStatus } from '../product'
import { ScientificFigureStudio } from './ScientificFigureStudio'

const STATUS_COPY: Record<ScientificTenItemStatus, { label: string; tone: string }> = {
  evidence_bound: { label: '已有证据', tone: 'is-evidence' },
  conditional: { label: '有条件', tone: 'is-conditional' },
  pending: { label: '待补充', tone: 'is-pending' },
}

export interface ScientificTenPanelProps {
  project: Project
}

export function ScientificTenPanel({ project }: ScientificTenPanelProps) {
  const proposal = project.discovery.scientificTen
  const selectedIdea = project.discovery.ideaCards.find((idea) => (
    idea.id === project.discovery.selectedIdeaId
  ))

  if (!proposal) {
    return (
      <section className="scientific-ten scientific-ten--empty" aria-labelledby="scientific-ten-title">
        <span className="scientific-ten__empty-icon"><ClipboardList size={24} aria-hidden="true" /></span>
        <div>
          <span className="product-eyebrow">SCIENTIFIC TEN</span>
          <h2 id="scientific-ten-title">生成科学十项研究方案</h2>
          <p>系统将使用当前项目的 GapCard、已选假设、变量与资源篮生成草案；缺失信息会明确保留为待补充。</p>
        </div>
        <button
          type="button"
          className="product-button is-primary"
          disabled={!selectedIdea}
          onClick={() => frontendDataSource.generateScientificTen(project.id)}
        >
          <Sparkles size={15} aria-hidden="true" />
          {selectedIdea ? '生成十项草案' : '请先选择候选假设'}
        </button>
      </section>
    )
  }

  const confirmedCount = proposal.items.filter((item) => item.confirmed).length
  const allItemsConfirmed = confirmedCount === proposal.items.length

  return (
    <section className={`scientific-ten ${proposal.status === 'confirmed' ? 'is-confirmed' : ''}`} aria-labelledby="scientific-ten-title">
      <header className="scientific-ten__header">
        <span className="scientific-ten__header-icon">
          {proposal.status === 'confirmed'
            ? <CheckCircle2 size={20} aria-hidden="true" />
            : <ClipboardList size={20} aria-hidden="true" />}
        </span>
        <div>
          <span className="product-eyebrow">SCIENTIFIC TEN · 研究方案</span>
          <h2 id="scientific-ten-title">科学十项</h2>
          <p>逐项核对内容、证据状态和未决动作；编辑后该项会自动恢复为待确认。</p>
        </div>
        <span className="scientific-ten__progress">
          <strong>{confirmedCount}/10</strong>
          <small>{proposal.status === 'confirmed' ? '方案已确认' : '已核对'}</small>
        </span>
      </header>

      <div className="scientific-ten__progressbar" aria-hidden="true">
        <i style={{ width: `${confirmedCount * 10}%` }} />
      </div>

      <ScientificFigureStudio project={project} />

      <div className="scientific-ten__items">
        {proposal.items.map((item) => {
          const status = STATUS_COPY[item.status]
          return (
            <details className={`scientific-ten__item ${item.confirmed ? 'is-confirmed' : ''}`} key={item.itemNo}>
              <summary>
                <span className="scientific-ten__number">
                  {item.confirmed ? <Check size={13} aria-hidden="true" /> : item.itemNo}
                </span>
                <span className="scientific-ten__title">
                  <strong>{item.title}</strong>
                  <small>{item.confirmed ? '已核对，可进入总确认' : '展开查看并确认本项'}</small>
                </span>
                <span className={`scientific-ten__status ${status.tone}`}>{status.label}</span>
                <ChevronDown size={15} aria-hidden="true" />
              </summary>

              <div className="scientific-ten__item-body">
                <label>
                  <span>方案内容</span>
                  <textarea
                    rows={5}
                    defaultValue={item.content}
                    onBlur={(event) => {
                      if (event.currentTarget.value !== item.content) {
                        frontendDataSource.updateScientificTenItem(project.id, item.itemNo, {
                          content: event.currentTarget.value,
                        })
                      }
                    }}
                  />
                </label>

                <div className="scientific-ten__meta">
                  <section>
                    <strong>证据引用</strong>
                    {item.evidenceRefs.length ? (
                      <div>{item.evidenceRefs.map((ref) => <span key={ref}>{ref}</span>)}</div>
                    ) : <p>当前没有可绑定的项目证据。</p>}
                  </section>
                  <label>
                    <span>未决动作</span>
                    <textarea
                      rows={Math.max(2, Math.min(5, item.unresolvedActions.length + 1))}
                      defaultValue={item.unresolvedActions.join('\n')}
                      placeholder="每行一条；没有未决动作时可留空"
                      onBlur={(event) => {
                        const next = event.currentTarget.value
                          .split('\n')
                          .map((value) => value.trim())
                          .filter(Boolean)
                        if (next.join('\n') !== item.unresolvedActions.join('\n')) {
                          frontendDataSource.updateScientificTenItem(project.id, item.itemNo, {
                            unresolvedActions: next,
                          })
                        }
                      }}
                    />
                  </label>
                </div>

                <button
                  type="button"
                  className={`scientific-ten__confirm-item ${item.confirmed ? 'is-confirmed' : ''}`}
                  onClick={() => frontendDataSource.updateScientificTenItem(project.id, item.itemNo, {
                    confirmed: !item.confirmed,
                  })}
                >
                  {item.confirmed
                    ? <CheckCircle2 size={15} aria-hidden="true" />
                    : <Circle size={15} aria-hidden="true" />}
                  {item.confirmed ? '已核对本项' : '确认本项内容与边界'}
                </button>
              </div>
            </details>
          )
        })}
      </div>

      <footer className="scientific-ten__footer">
        <span>
          {proposal.status === 'confirmed'
            ? <CheckCircle2 size={18} aria-hidden="true" />
            : <FileWarning size={18} aria-hidden="true" />}
        </span>
        <div>
          <strong>{proposal.status === 'confirmed' ? '科学十项方案已确认' : '完成十项核对后再确认整套方案'}</strong>
          <p>总确认只冻结当前项目中的方案草案；H1、H2、数据执行和结论授权仍需分别通过。</p>
        </div>
        {proposal.status !== 'confirmed' && (
          <button
            type="button"
            className="product-button is-primary"
            disabled={!allItemsConfirmed}
            onClick={() => frontendDataSource.confirmScientificTen(project.id)}
          >
            <CheckCircle2 size={15} aria-hidden="true" />
            确认科学十项方案
          </button>
        )}
      </footer>
    </section>
  )
}
