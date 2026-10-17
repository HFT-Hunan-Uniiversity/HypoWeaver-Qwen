/**
 * 碳市场展示稿：只在"那一个"主碳市场案例上，研究提案一步默认展示旧版期刊初稿。
 * 规则显式可改：后端原始题名完全等于下列之一，或项目 id 以下列前缀开头。
 * 不用 displayProjectTitle 的虚拟题名；带括注尾巴的验收/测试项目不匹配。
 */
export const SHOWCASE_TITLES: readonly string[] = [
  '碳市场与企业绿色创新',
  '碳市场行业同群暴露与企业绿色发明',
  '碳市场能否激励企业高质量绿色创新？——基于公开上市公司面板的复现证据',
]
export const SHOWCASE_ID_PREFIXES: readonly string[] = ['pr_0ff7114a']

export function isShowcaseProject(
  rawTitle: string | null | undefined,
  id?: string | null,
): boolean {
  const t = (rawTitle || '').trim()
  if (t && SHOWCASE_TITLES.includes(t)) return true
  return !!id && SHOWCASE_ID_PREFIXES.some((p) => id.startsWith(p))
}
