/**
 * TaskComposer：ClawsGO /chat 形态的「新研究」页。
 * 问候语（逐字 blur 入场）→ 分类 chips → 模板卡片 2 列 → 底部居中输入框。
 * 提交文本 → 创建前端演示项目；导入案例文件夹 → 走真实链路（App 处理）。
 */
import { ArrowUp, ChevronDown, FolderUp, Link2, Settings2, SlidersHorizontal } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import type { CaseImportReport, RuntimeConfigStatus } from '../runtime/types'
import type { MockMode } from '../data/mockPipeline'

type LaunchTarget = 'hypoweaver' | 'agent-laboratory'

interface TemplateCard {
  id: string
  title: string
  description: string
  prompt: string
  mode: MockMode
}

interface TemplateCategory {
  id: string
  label: string
  cards: TemplateCard[]
}

/** 模板任务：取材于 benchmark 案例，静态数据即可。 */
const TEMPLATE_CATEGORIES: TemplateCategory[] = [
  {
    id: 'policy', label: '政策评估',
    cards: [
      { id: 'case_002', title: '绿色信贷与高污染企业', description: '绿色信贷政策约束下，高污染企业的授信、投资与转型行为如何变化。', prompt: '研究绿色信贷政策对高污染企业新增授信与转型行为的因果效应，企业-年份面板，2012–2022。', mode: 'discovery_blind' },
      { id: 'case_009', title: '绿改试验区与空气质量', description: '绿色金融改革创新试验区设立对城市空气质量的处理效应。', prompt: '评估绿色金融改革创新试验区设立对城市空气质量指数的因果影响，城市面板，试点作为准自然实验。', mode: 'reproduction_aligned' },
    ],
  },
  {
    id: 'firm', label: '企业行为',
    cards: [
      { id: 'case_006', title: '绿色金融与企业环境投资', description: '绿色金融发展水平如何影响企业环境治理投资的规模与结构。', prompt: '研究地区绿色金融发展水平对企业环境治理投资的影响与作用机制。', mode: 'discovery_blind' },
      { id: 'case_005', title: '农业绿色金融', description: '农业绿色金融支持与农业企业绿色生产率的关系与机制。', prompt: '检验农业绿色金融支持对农业企业绿色全要素生产率的影响，识别融资约束缓解机制。', mode: 'reproduction_aligned' },
    ],
  },
  {
    id: 'region', label: '区域发展',
    cards: [
      { id: 'case_004', title: '绿色金融地方竞争与产业转型', description: '地方政府绿色金融竞争对区域产业结构转型的推动作用。', prompt: '研究地方绿色金融竞争强度与区域产业结构高级化之间的因果关系。', mode: 'discovery_blind' },
      { id: 'case_008', title: '绿色金融与可持续发展', description: '绿色金融发展对区域可持续发展指数的贡献及空间溢出。', prompt: '评估绿色金融发展水平对区域可持续发展的影响，考虑空间溢出效应。', mode: 'reproduction_aligned' },
    ],
  },
  {
    id: 'market', label: '市场反应',
    cards: [
      { id: 'case_010', title: '央行绿色沟通与金融市场', description: '央行绿色政策沟通事件对债券与股票市场的短期反应。', prompt: '用事件研究法检验央行绿色沟通对绿色债券利差与相关股票收益的短期影响。', mode: 'reproduction_aligned' },
      { id: 'case_007', title: '数字绿色金融与经济韧性', description: '数字化绿色金融发展对城市经济韧性的提升效应。', prompt: '研究数字绿色金融发展指数对城市经济韧性的影响与异质性来源。', mode: 'discovery_blind' },
    ],
  },
]

const MODE_TEXT: Record<MockMode, string> = {
  discovery_blind: '盲态发现',
  reproduction_aligned: '对齐复现',
}

function greetingByHour(): string {
  const hour = new Date().getHours()
  if (hour < 5) return '夜深了'
  if (hour < 12) return '上午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

const directoryInputAttributes = { webkitdirectory: '', directory: '' }

interface TaskComposerProps {
  config: RuntimeConfigStatus | null
  importReport: CaseImportReport | null
  busy: boolean
  busyLabel: string
  onImportCaseFolder: (files: File[], target: LaunchTarget) => Promise<void>
  onImportGroup1Handoff: (path: string, mode: 'research' | 'fixture') => Promise<void>
  onOpenAdvanced: () => void
  onOpenSettings: () => void
  onCreateProject: (prompt: string, mode: MockMode) => void
}

export function TaskComposer({ config, importReport, busy, busyLabel, onImportCaseFolder, onImportGroup1Handoff, onOpenAdvanced, onOpenSettings, onCreateProject }: TaskComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [target, setTarget] = useState<LaunchTarget>('hypoweaver')
  const [category, setCategory] = useState(TEMPLATE_CATEGORIES[0].id)
  const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState<MockMode>('discovery_blind')
  const [moreOpen, setMoreOpen] = useState(false)
  const [group1Path, setGroup1Path] = useState('')
  const [group1Mode, setGroup1Mode] = useState<'research' | 'fixture'>('research')
  const qwenReady = Boolean(config?.qwenApiKey.configured)
  const greeting = useMemo(() => `${greetingByHour()}，研究者`, [])
  const cards = TEMPLATE_CATEGORIES.find((item) => item.id === category)?.cards ?? []

  function chooseFile(nextTarget: LaunchTarget) {
    setTarget(nextTarget)
    setMoreOpen(false)
    fileInputRef.current?.click()
  }

  function pickTemplate(card: TemplateCard) {
    setPrompt(card.prompt)
    setMode(card.mode)
  }

  function submit() {
    const text = prompt.trim()
    if (!text || busy) return
    onCreateProject(text, mode)
  }

  return (
    <div className="composer">
      <input
        ref={fileInputRef}
        className="file-input-hidden"
        type="file"
        multiple
        {...directoryInputAttributes}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? [])
          event.currentTarget.value = ''
          if (files.length) void onImportCaseFolder(files, target)
        }}
      />

      <div className="composer__scroll">
        <div className="composer__center">
          <h1 className="composer__greeting" aria-label={greeting}>
            {greeting.split('').map((char, index) => (
              <span key={`${char}-${index}`} style={{ animationDelay: `${index * 45}ms` }}>{char}</span>
            ))}
          </h1>
          <p className="composer__demo-badge">Group 1 冻结包 → 可行性包与科学十项 → Group 2 H1/H2 设计审查</p>
          <p className="composer__lead">描述一个研究目标，先建立项目并完成研究发现，再决定是否交接到正式 H1–H4。</p>

          <div className="composer__chips" role="tablist" aria-label="任务模板分类">
            {TEMPLATE_CATEGORIES.map((item) => (
              <button
                type="button"
                role="tab"
                key={item.id}
                aria-selected={category === item.id}
                className={`composer__chip ${category === item.id ? 'is-active' : ''}`}
                onClick={() => setCategory(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="composer__cards" key={category}>
            {cards.map((card) => (
              <button type="button" className="composer__card" key={card.id} onClick={() => pickTemplate(card)}>
                <h3>{card.title}</h3>
                <p>{card.description}</p>
                <small>{MODE_TEXT[card.mode]} · {card.id}</small>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="composer__dock">
        {importReport && (
          <p className="composer__import">
            已导入 {importReport.datasetFilename} · {importReport.rowCount.toLocaleString()} 行 × {importReport.columnCount} 列 · 隔离 {importReport.hiddenFileCount} 份隐藏材料
          </p>
        )}
        <div className="composer__group1">
          <div><Link2 size={15} /><span><strong>Group 1 → Group 2</strong> 校验哈希、生成可行性包和科学十项草案，再进入 H1</span></div>
          <input
            value={group1Path}
            placeholder="粘贴 Group 1 pilot 根目录或 I_group1_handoff 路径"
            aria-label="Group 1 冻结交接包路径"
            onChange={(event) => setGroup1Path(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && group1Path.trim() && !busy) {
                event.preventDefault()
                void onImportGroup1Handoff(group1Path, group1Mode)
              }
            }}
          />
          <select value={group1Mode} onChange={(event) => setGroup1Mode(event.target.value as 'research' | 'fixture')} aria-label="Group 1 接入运行模式">
            <option value="research">真实研究 · 调用模型</option>
            <option value="fixture">离线验收 · 不调用模型</option>
          </select>
          <button type="button" disabled={busy || !group1Path.trim()} onClick={() => void onImportGroup1Handoff(group1Path, group1Mode)}>
            {busy ? (busyLabel || '正在接入…') : '校验并进入 H1'}
          </button>
        </div>
        <form
          className="composer__box"
          onSubmit={(event) => { event.preventDefault(); submit() }}
        >
          <textarea
            value={prompt}
            rows={2}
            placeholder="描述你的研究任务，或导入案例数据包…"
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                submit()
              }
            }}
          />
          <div className="composer__box-row">
            <div className="composer__box-left">
              <div className="composer__more">
                <button type="button" className="composer__tool" aria-haspopup="menu" aria-expanded={moreOpen} onClick={() => setMoreOpen((current) => !current)}>
                  <SlidersHorizontal size={14} />更多选项
                </button>
                {moreOpen && (
                  <div className="composer__menu" role="menu">
                    <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onOpenAdvanced() }}>手动填写研究输入</button>
                    <button type="button" role="menuitem" disabled={busy || !qwenReady} onClick={() => chooseFile('agent-laboratory')}>{qwenReady ? '导入案例到 Agent Laboratory 基线' : '基线需先配置千问'}</button>
                    <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onOpenSettings() }}><Settings2 size={13} />模型与执行器配置</button>
                  </div>
                )}
              </div>
              <button type="button" className="composer__tool" disabled={busy} onClick={() => chooseFile('hypoweaver')}>
                <FolderUp size={14} />{busy ? (busyLabel || '正在处理…') : '导入案例文件夹'}
              </button>
              <label className="composer__mode">
                <select value={mode} onChange={(event) => setMode(event.target.value as MockMode)} aria-label="研究模式">
                  <option value="discovery_blind">盲态发现</option>
                  <option value="reproduction_aligned">对齐复现</option>
                </select>
                <ChevronDown size={13} aria-hidden="true" />
              </label>
            </div>
            <button type="submit" className="composer__send" disabled={busy || !prompt.trim()} aria-label="创建研究项目">
              <ArrowUp size={16} />
            </button>
          </div>
        </form>
        <p className="composer__hint">Group 1 冻结包通过 H1 后可继续到 Group 2 设计与 H2；数据和执行器缺口只在统计执行前拦截。</p>
      </div>
    </div>
  )
}
