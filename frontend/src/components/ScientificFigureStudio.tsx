import { useEffect, useRef, useState } from 'react'
import { Download, Languages, LineChart, Palette, ShieldCheck, Sparkles } from 'lucide-react'
import {
  frontendDataSource,
  type Project,
  type ResearchFigureLanguage,
  type ScientificFigureCopy,
  type ScientificFigureDraft,
} from '../product'

const KIND_LABELS: Record<ScientificFigureDraft['kind'], Record<ResearchFigureLanguage, string>> = {
  mechanism: { zh: '机制路径', en: 'Mechanism' },
  coefficient: { zh: '系数图', en: 'Coefficient' },
  event_study: { zh: '事件研究', en: 'Event study' },
  trend: { zh: '趋势图', en: 'Trends' },
}

const PALETTE = {
  ink: '#172b4d',
  muted: '#64748b',
  grid: '#dce4ea',
  teal: '#178f83',
  tealSoft: '#dff2ee',
  gold: '#d79a2b',
  coral: '#d76555',
  paper: '#fbfaf7',
}

function trimLabel(value: string, limit = 20): string {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value
}

function FigureText({ copy }: { copy: ScientificFigureCopy }) {
  return (
    <>
      <text x="44" y="43" fill={PALETTE.ink} fontSize="21" fontWeight="700">{trimLabel(copy.title, 48)}</text>
      <text x="44" y="68" fill={PALETTE.muted} fontSize="11.5">{trimLabel(copy.subtitle, 75)}</text>
    </>
  )
}

function MechanismPreview({ figure, language }: { figure: ScientificFigureDraft; language: ResearchFigureLanguage }) {
  const copy = figure.copy[language]
  const nodes = figure.nodes ?? []
  const mainNodes = nodes.filter((node) => node.role !== 'boundary').slice(0, 3)
  const boundary = nodes.find((node) => node.role === 'boundary')
  const positions = [92, 300, 508]
  return (
    <>
      <defs>
        <marker id={`arrow-${figure.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill={PALETTE.teal} />
        </marker>
      </defs>
      <FigureText copy={copy} />
      {mainNodes.map((node, index) => {
        const x = positions[index]
        const label = language === 'zh' ? node.labelZh : node.labelEn
        return (
          <g key={node.id}>
            {index < mainNodes.length - 1 && (
              <line
                x1={x + 126}
                y1="185"
                x2={positions[index + 1] - 15}
                y2="185"
                stroke={PALETTE.teal}
                strokeWidth="2.6"
                markerEnd={`url(#arrow-${figure.id})`}
              />
            )}
            <rect x={x - 15} y="137" width="142" height="96" rx="16" fill={index === 1 ? PALETTE.tealSoft : '#ffffff'} stroke={index === 1 ? PALETTE.teal : PALETTE.grid} strokeWidth="1.5" />
            <circle cx={x + 12} cy="163" r="6" fill={index === 1 ? PALETTE.gold : PALETTE.teal} />
            <text x={x + 56} y="188" textAnchor="middle" fill={PALETTE.ink} fontSize="14" fontWeight="700">{trimLabel(label, 15)}</text>
            <text x={x + 56} y="211" textAnchor="middle" fill={PALETTE.muted} fontSize="10.5">
              {language === 'zh'
                ? ['解释变量', '待检验机制', '结果变量'][index]
                : ['Predictor', 'Mechanism', 'Outcome'][index]}
            </text>
          </g>
        )
      })}
      {boundary && (
        <g>
          <line x1="371" y1="298" x2="371" y2="241" stroke={PALETTE.gold} strokeWidth="2" strokeDasharray="5 5" markerEnd={`url(#arrow-${figure.id})`} />
          <rect x="292" y="299" width="158" height="54" rx="12" fill="#fff8e8" stroke={PALETTE.gold} />
          <text x="371" y="322" textAnchor="middle" fill={PALETTE.ink} fontSize="12" fontWeight="700">
            {trimLabel(language === 'zh' ? boundary.labelZh : boundary.labelEn, 18)}
          </text>
          <text x="371" y="340" textAnchor="middle" fill={PALETTE.muted} fontSize="9.5">{language === 'zh' ? '边界条件' : 'Boundary condition'}</text>
        </g>
      )}
      <text x="44" y="390" fill={PALETTE.muted} fontSize="10.5">{copy.legend.join('  ·  ')}</text>
    </>
  )
}

function AxisLabels({ copy }: { copy: ScientificFigureCopy }) {
  return (
    <>
      <text x="374" y="396" textAnchor="middle" fill={PALETTE.muted} fontSize="11">{copy.xLabel}</text>
      <text x="15" y="235" textAnchor="middle" fill={PALETTE.muted} fontSize="11" transform="rotate(-90 15 235)">{copy.yLabel}</text>
    </>
  )
}

function PreviewWatermark({ language }: { language: ResearchFigureLanguage }) {
  return (
    <g opacity="0.66">
      <rect x="475" y="372" width="200" height="24" rx="12" fill="#fff0eb" />
      <text x="575" y="388" textAnchor="middle" fill={PALETTE.coral} fontSize="10" fontWeight="700">
        {language === 'zh' ? '模拟数据 · 仅预览样式' : 'SYNTHETIC DATA · STYLE PREVIEW'}
      </text>
    </g>
  )
}

function CoefficientPreview({ copy, language }: { copy: ScientificFigureCopy; language: ResearchFigureLanguage }) {
  const rows = language === 'zh'
    ? ['主效应', '机制检验', '高暴露组', '低暴露组']
    : ['Main effect', 'Mechanism', 'High exposure', 'Low exposure']
  const values = [0.58, 0.35, 0.77, 0.19]
  const intervals = [[0.32, 0.84], [0.08, 0.62], [0.43, 1.11], [-0.08, 0.46]]
  const x = (value: number) => 310 + value * 220
  return (
    <>
      <FigureText copy={copy} />
      {[0, 0.5, 1].map((tick) => <line key={tick} x1={x(tick)} y1="108" x2={x(tick)} y2="340" stroke={PALETTE.grid} strokeWidth="1" />)}
      <line x1={x(0)} y1="102" x2={x(0)} y2="343" stroke={PALETTE.muted} strokeDasharray="4 4" />
      {rows.map((row, index) => {
        const y = 140 + index * 57
        return (
          <g key={row}>
            <text x="275" y={y + 4} textAnchor="end" fill={PALETTE.ink} fontSize="12.5">{row}</text>
            <line x1={x(intervals[index][0])} y1={y} x2={x(intervals[index][1])} y2={y} stroke={PALETTE.teal} strokeWidth="3" />
            <circle cx={x(values[index])} cy={y} r="6" fill={index === 2 ? PALETTE.gold : PALETTE.teal} stroke="#fff" strokeWidth="2" />
          </g>
        )
      })}
      <AxisLabels copy={copy} />
      <PreviewWatermark language={language} />
    </>
  )
}

function EventStudyPreview({ copy, language }: { copy: ScientificFigureCopy; language: ResearchFigureLanguage }) {
  const points = [-0.04, 0.02, -0.01, 0, 0.17, 0.31, 0.4, 0.46, 0.51]
  const x = (index: number) => 102 + index * 65
  const y = (value: number) => 300 - value * 300
  return (
    <>
      <FigureText copy={copy} />
      {[0, 0.25, 0.5].map((tick) => <line key={tick} x1="82" y1={y(tick)} x2="646" y2={y(tick)} stroke={PALETTE.grid} />)}
      <line x1="82" y1={y(0)} x2="646" y2={y(0)} stroke={PALETTE.muted} />
      <line x1={x(3.5)} y1="105" x2={x(3.5)} y2="322" stroke={PALETTE.gold} strokeWidth="1.5" strokeDasharray="5 5" />
      <polyline points={points.map((value, index) => `${x(index)},${y(value)}`).join(' ')} fill="none" stroke={PALETTE.teal} strokeWidth="2.4" />
      {points.map((value, index) => (
        <g key={index}>
          <line x1={x(index)} y1={y(value - 0.08)} x2={x(index)} y2={y(value + 0.08)} stroke={PALETTE.teal} strokeWidth="1.5" />
          <circle cx={x(index)} cy={y(value)} r="4.5" fill={index >= 4 ? PALETTE.teal : '#fff'} stroke={PALETTE.teal} strokeWidth="2" />
          <text x={x(index)} y="342" textAnchor="middle" fill={PALETTE.muted} fontSize="9.5">{index - 4}</text>
        </g>
      ))}
      <AxisLabels copy={copy} />
      <PreviewWatermark language={language} />
    </>
  )
}

function TrendPreview({ copy, language }: { copy: ScientificFigureCopy; language: ResearchFigureLanguage }) {
  const treated = [0.2, 0.25, 0.28, 0.32, 0.48, 0.66, 0.81]
  const comparison = [0.18, 0.23, 0.26, 0.31, 0.37, 0.42, 0.47]
  const x = (index: number) => 100 + index * 86
  const y = (value: number) => 330 - value * 250
  const line = (values: number[]) => values.map((value, index) => `${x(index)},${y(value)}`).join(' ')
  return (
    <>
      <FigureText copy={copy} />
      {[0.2, 0.5, 0.8].map((tick) => <line key={tick} x1="82" y1={y(tick)} x2="642" y2={y(tick)} stroke={PALETTE.grid} />)}
      <line x1={x(3.5)} y1="107" x2={x(3.5)} y2="334" stroke={PALETTE.gold} strokeWidth="1.5" strokeDasharray="5 5" />
      <polyline points={line(comparison)} fill="none" stroke={PALETTE.muted} strokeWidth="2.4" />
      <polyline points={line(treated)} fill="none" stroke={PALETTE.teal} strokeWidth="3" />
      {treated.map((value, index) => <circle key={index} cx={x(index)} cy={y(value)} r="4" fill={PALETTE.teal} />)}
      <g transform="translate(465 105)">
        <line x1="0" y1="0" x2="22" y2="0" stroke={PALETTE.teal} strokeWidth="3" />
        <text x="29" y="4" fill={PALETTE.ink} fontSize="10">{copy.legend[0]}</text>
        <line x1="0" y1="22" x2="22" y2="22" stroke={PALETTE.muted} strokeWidth="2.4" />
        <text x="29" y="26" fill={PALETTE.ink} fontSize="10">{copy.legend[1]}</text>
      </g>
      <AxisLabels copy={copy} />
      <PreviewWatermark language={language} />
    </>
  )
}

function FigurePreview({ figure, language }: { figure: ScientificFigureDraft; language: ResearchFigureLanguage }) {
  const copy = figure.copy[language]
  return (
    <svg
      className="figure-studio__svg"
      viewBox="0 0 720 420"
      role="img"
      aria-label={copy.title}
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="720" height="420" rx="18" fill={PALETTE.paper} />
      {figure.kind === 'mechanism' && <MechanismPreview figure={figure} language={language} />}
      {figure.kind === 'coefficient' && <CoefficientPreview copy={copy} language={language} />}
      {figure.kind === 'event_study' && <EventStudyPreview copy={copy} language={language} />}
      {figure.kind === 'trend' && <TrendPreview copy={copy} language={language} />}
    </svg>
  )
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('width', '1440')
  clone.setAttribute('height', '840')
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  return new XMLSerializer().serializeToString(clone)
}

function exportSvg(svg: SVGSVGElement, filename: string) {
  downloadBlob(new Blob([serializeSvg(svg)], { type: 'image/svg+xml;charset=utf-8' }), `${filename}.svg`)
}

function exportPng(svg: SVGSVGElement, filename: string) {
  const source = serializeSvg(svg)
  const url = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml;charset=utf-8' }))
  const image = new Image()
  image.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = 1440
    canvas.height = 840
    const context = canvas.getContext('2d')
    if (!context) return
    context.fillStyle = PALETTE.paper
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => {
      if (blob) downloadBlob(blob, `${filename}.png`)
      URL.revokeObjectURL(url)
    }, 'image/png')
  }
  image.src = url
}

export function ScientificFigureStudio({ project }: { project: Project }) {
  const proposal = project.discovery.scientificTen
  const figures = proposal?.figures ?? []
  const language = proposal?.figureLanguage ?? 'zh'
  const [selectedId, setSelectedId] = useState(figures[0]?.id ?? '')
  const previewRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!figures.some((figure) => figure.id === selectedId)) setSelectedId(figures[0]?.id ?? '')
  }, [figures, selectedId])

  if (!proposal) return null
  if (!figures.length) {
    return (
      <section className="figure-studio figure-studio--empty">
        <span><LineChart size={20} aria-hidden="true" /></span>
        <div>
          <strong>为这套科学十项补充绘图方案</strong>
          <p>根据假设、变量和数据结构生成研究设计图与统计图计划；不会生成或冒充实证结果。</p>
        </div>
        <button type="button" className="product-button is-primary" onClick={() => frontendDataSource.generateScientificFigures(project.id)}>
          <Sparkles size={15} aria-hidden="true" />生成绘图方案
        </button>
      </section>
    )
  }

  const selected = figures.find((figure) => figure.id === selectedId) ?? figures[0]
  const copy = selected.copy[language]
  const filename = `hypoweaver-${selected.kind}-${language}`
  const commitCopy = (patch: Partial<ScientificFigureCopy>) => {
    frontendDataSource.updateScientificFigureCopy(project.id, selected.id, language, patch)
  }
  const currentSvg = () => previewRef.current?.querySelector('svg') ?? null

  return (
    <section className="figure-studio" aria-labelledby="figure-studio-title">
      <header className="figure-studio__header">
        <span className="figure-studio__icon"><Palette size={20} aria-hidden="true" /></span>
        <div>
          <span className="product-eyebrow">RESEARCH FIGURES · 科研绘图</span>
          <h3 id="figure-studio-title">科学十项绘图工作台</h3>
          <p>先规划应画什么，再在模型完成后接入真实估计；研究设计图可立即使用。</p>
        </div>
        <div className="figure-studio__language" aria-label="图中文字语言">
          <Languages size={14} aria-hidden="true" />
          {(['zh', 'en'] as const).map((item) => (
            <button
              type="button"
              className={language === item ? 'is-active' : ''}
              key={item}
              onClick={() => frontendDataSource.setScientificFigureLanguage(project.id, item)}
            >
              {item === 'zh' ? '中文' : 'English'}
            </button>
          ))}
        </div>
      </header>

      <div className="figure-studio__tabs" role="tablist" aria-label="绘图方案">
        {figures.map((figure) => (
          <button
            type="button"
            role="tab"
            aria-selected={figure.id === selected.id}
            className={figure.id === selected.id ? 'is-active' : ''}
            key={figure.id}
            onClick={() => setSelectedId(figure.id)}
          >
            <span>{KIND_LABELS[figure.kind][language]}</span>
            <small>{figure.dataStatus === 'project_bound'
              ? (language === 'zh' ? '设计已绑定' : 'Design bound')
              : (language === 'zh' ? '等待估计' : 'Awaiting estimates')}</small>
          </button>
        ))}
      </div>

      <div className="figure-studio__workspace">
        <div className="figure-studio__preview" ref={previewRef}>
          <FigurePreview figure={selected} language={language} />
          <div className={`figure-studio__status ${selected.dataStatus === 'project_bound' ? 'is-bound' : ''}`}>
            {selected.dataStatus === 'project_bound'
              ? <><ShieldCheck size={13} aria-hidden="true" />{language === 'zh' ? '绑定当前研究设计' : 'Bound to current research design'}</>
              : <><LineChart size={13} aria-hidden="true" />{language === 'zh' ? '正式图等待真实估计' : 'Publication figure awaits verified estimates'}</>}
          </div>
        </div>

        <aside className="figure-studio__editor" key={`${selected.id}-${language}`}>
          <div className="figure-studio__editor-head">
            <div>
              <strong>{language === 'zh' ? '图中文字' : 'Figure copy'}</strong>
              <small>{language === 'zh' ? '当前编辑中文版本' : 'Editing the English version'}</small>
            </div>
          </div>
          <label>
            <span>{language === 'zh' ? '标题' : 'Title'}</span>
            <input defaultValue={copy.title} onBlur={(event) => event.currentTarget.value !== copy.title && commitCopy({ title: event.currentTarget.value })} />
          </label>
          <label>
            <span>{language === 'zh' ? '副标题' : 'Subtitle'}</span>
            <textarea rows={2} defaultValue={copy.subtitle} onBlur={(event) => event.currentTarget.value !== copy.subtitle && commitCopy({ subtitle: event.currentTarget.value })} />
          </label>
          {selected.kind !== 'mechanism' && (
            <div className="figure-studio__axis-fields">
              <label>
                <span>{language === 'zh' ? '横轴' : 'X axis'}</span>
                <input defaultValue={copy.xLabel} onBlur={(event) => event.currentTarget.value !== copy.xLabel && commitCopy({ xLabel: event.currentTarget.value })} />
              </label>
              <label>
                <span>{language === 'zh' ? '纵轴' : 'Y axis'}</span>
                <input defaultValue={copy.yLabel} onBlur={(event) => event.currentTarget.value !== copy.yLabel && commitCopy({ yLabel: event.currentTarget.value })} />
              </label>
            </div>
          )}
          <label>
            <span>{language === 'zh' ? '图例（每行一项）' : 'Legend (one item per line)'}</span>
            <textarea
              rows={2}
              defaultValue={copy.legend.join('\n')}
              onBlur={(event) => {
                const legend = event.currentTarget.value.split('\n').map((value) => value.trim()).filter(Boolean)
                if (legend.join('\n') !== copy.legend.join('\n')) commitCopy({ legend })
              }}
            />
          </label>
          <div className="figure-studio__export">
            <button type="button" onClick={() => { const svg = currentSvg(); if (svg) exportSvg(svg, filename) }}>
              <Download size={14} aria-hidden="true" />SVG
            </button>
            <button type="button" onClick={() => { const svg = currentSvg(); if (svg) exportPng(svg, filename) }}>
              <Download size={14} aria-hidden="true" />PNG
            </button>
          </div>
        </aside>
      </div>

      <footer className="figure-studio__boundary">
        <ShieldCheck size={15} aria-hidden="true" />
        <p>{language === 'zh'
          ? '科学边界：统计图当前使用醒目标注的模拟数据预览版式。只有接入实际模型输出与置信区间后，才能导出为正式结果图。'
          : 'Scientific boundary: statistical charts use clearly marked synthetic data for style preview. Export as results only after verified model outputs and confidence intervals are connected.'}</p>
      </footer>
    </section>
  )
}
