/**
 * 前端展示用项目标题：去掉旧 demo「Codex实测」等字样，不改后端记录。
 */
export function displayProjectTitle(title: string | undefined | null): string {
  const t = (title || '').trim()
  if (!t) return 'HypoWeaver · 分步向导'
  if (/Codex\s*实测/i.test(t) || /^I\s*向导[·･.•]?Codex/i.test(t)) {
    return 'HypoWeaver · 分步向导'
  }
  // 其它仍含 Codex 的演示标签 → 千问
  if (/Codex/i.test(t)) return t.replace(/Codex/gi, '千问')
  return t
}
