/**
 * 每位访客自己的模型密钥：只存在本浏览器 localStorage，随请求放进请求头
 * （X-LLM-API-Key / X-LLM-Model），服务器只在这一次请求里使用，不会保存。
 */
const KEY = 'hw.llm.apiKey'
const MODEL = 'hw.llm.model'

function read(name: string): string {
  try {
    return localStorage.getItem(name) || ''
  } catch {
    return ''
  }
}
function write(name: string, value: string) {
  try {
    if (value) localStorage.setItem(name, value)
    else localStorage.removeItem(name)
  } catch {
    /* 隐私模式等无法写入时忽略 */
  }
}

export const getBrowserKey = () => read(KEY).trim()
export const setBrowserKey = (value: string) => write(KEY, value.trim())
export const getBrowserModel = () => read(MODEL).trim()
export const setBrowserModel = (value: string) => write(MODEL, value.trim())

/** 附加到每个 /api 请求的模型请求头（未填写时为空对象） */
export function llmHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const key = getBrowserKey()
  const model = getBrowserModel()
  if (key) headers['X-LLM-API-Key'] = key
  if (model) headers['X-LLM-Model'] = model
  return headers
}
