/**
 * 碳市场展示稿：碳市场项目的研究提案一步默认展示旧版"期刊规范化初稿"。
 * 识别以后端原始题名为准（不用 displayProjectTitle 的虚拟题名，以免把演示壳误认成碳市场）。
 */
export function isShowcaseProject(rawTitle: string | null | undefined): boolean {
  return /碳市场|碳排放权交易|碳交易/.test(rawTitle || '')
}
