/**
 * 前端展示用项目标题：把验收/演示编码藏到虚拟中文题名后，不改后端记录。
 */

const VIRTUAL_TITLES = [
  '碳市场同群与绿色创新',
  '环境规制与企业研发',
  '数字化与全要素生产率',
  '供应链韧性与出口',
  '绿色信贷与技术创新',
  '城市群协同与产业升级',
  '税收激励与人力资本',
  '贸易自由化与企业绩效',
] as const

const ACCEPTANCE =
  /I\s*向导|I\s*harness|\bharness\b|R\s*[0-9]|Codex|零手工|验收|端到端实测|可删除|长名称|多结果候选|继承绑定|审阅流程|流程验收|新项目（可删除）/i

function hashSeed(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h
}

function pickVirtual(seed: string): string {
  return VIRTUAL_TITLES[hashSeed(seed) % VIRTUAL_TITLES.length]
}

/** 是否属于验收/演示编码标题，需要换虚拟展示名 */
export function isAcceptanceTitle(title: string | undefined | null): boolean {
  return ACCEPTANCE.test((title || '').trim())
}

/**
 * @param seed 稳定选取虚拟题名用（推荐 project id）；缺省时用原标题哈希
 */
export function displayProjectTitle(
  title: string | undefined | null,
  seed?: string | null,
): string {
  const t = (title || '').trim()
  if (!t) return '未命名研究'

  // 去掉括号/间隔号里的验收尾巴，尽量保留学术题干
  let cleaned = t
    .replace(
      /[（(][^）)]*(?:R\s*\d|验收|零手工|Codex|实测|可删除|长名称|多结果|继承绑定|审阅流程|端到端|向导)[^）)]*[）)]/gi,
      '',
    )
    .replace(/\s*[·•･]\s*(?:R\s*\d.*|验收.*|零手工.*|Codex.*|新项目.*|端到端.*|含长说明.*)$/i, '')
    .replace(/^流程验收\s*[·•･]\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim()

  const key = (seed || t).trim() || t

  // 纯演示壳标题 / 仍含验收码 → 虚拟题名
  if (
    /^I\s*向导/i.test(t) ||
    /^I\s+\w+/i.test(t) ||
    /Codex\s*实测/i.test(t) ||
    /^流程验收/i.test(t) ||
    /\bharness\b/i.test(t)
  ) {
    return pickVirtual(key)
  }
  if (!cleaned || /^新项目/.test(cleaned) || ACCEPTANCE.test(cleaned) || ACCEPTANCE.test(t)) {
    // 题干已干净且不含验收词时用题干（例如「碳市场同群暴露与绿色创新」）
    if (cleaned && cleaned.length >= 4 && !ACCEPTANCE.test(cleaned) && !/^新项目/.test(cleaned)) {
      return cleaned
    }
    return pickVirtual(key)
  }
  return cleaned
}

/** Asia/Shanghai 时段问候 */
export function timeGreeting(now = new Date()): string {
  const hour = Number(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Shanghai',
      hour: 'numeric',
      hour12: false,
    }).format(now),
  )
  if (hour >= 5 && hour < 12) return '早上好'
  if (hour >= 12 && hour < 18) return '下午好'
  if (hour >= 18 && hour < 23) return '晚上好'
  return '夜深了'
}
