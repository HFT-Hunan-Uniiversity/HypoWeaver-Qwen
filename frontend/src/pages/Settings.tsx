import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { QWEN_MODELS, useLlm } from '../lib/llm'
interface Status {
  configured: boolean
  model: string
  message: string
  usage: { calls: number; input_tokens: number; output_tokens: number }
  sources: Record<string, { status: string; reason?: string }>
  recent_calls: {
    id: string
    prompt_name: string
    model: string
    input_tokens: number
    output_tokens: number
    latency_ms: number
    status: string
    error?: string
  }[]
}
const prompts: Record<string, string> = {
  connection_test: '测试连接',
  suggest_queries: '生成检索式',
  generate_candidates: '生成候选',
  review_candidates: '候选自审',
  draft_plan: '起草方案',
  suggest_bindings: '建议变量绑定',
  interpret_results: '解读结果',
  write_proposal_sections: '撰写提案',
}
export default function Settings() {
  const cache = useQueryClient(),
    [message, setMessage] = useState('')
  const q = useQuery({
    queryKey: ['settings'],
    queryFn: () => api<Status>('/settings/status'),
    staleTime: 60000,
  })
  const llm = useLlm()
  const [picked, setPicked] = useState('')
  const switchModel = useMutation({
    mutationFn: (model: string) => api('/settings/llm', body('PUT', { llm_model: model })),
    onSuccess: () => {
      setPicked('')
      for (const k of ['llm', 'settings']) cache.invalidateQueries({ queryKey: [k] })
    },
  })
  const models = QWEN_MODELS
  const test = useMutation({
    mutationFn: () => api<{ message: string }>('/settings/llm:test', body('POST')),
    onSuccess: (r) => setMessage(r.message),
    onSettled: () => {
      cache.invalidateQueries({ queryKey: ['settings'] })
    },
  })
  return (
    <div className="product-page">
      <p className="eyebrow">服务设置</p>
      <h1>服务与用量</h1>
      <p className="muted">密钥只在本机环境中配置，此页面不显示或保存密钥。</p>
      <ErrorNote error={q.error} />
      {q.isPending ? (
        <p>正在检查服务状态…</p>
      ) : (
        q.data && (
          <>
            <section className="panel">
              <h2>模型连接 · 千问</h2>
              <p>
                当前模型：
                <strong>
                  {llm.data?.llm_model || q.data.model || '未设置（默认 qwen-plus）'}
                </strong>{' '}
                · {(llm.data?.configured ?? q.data.configured) ? '已配置' : '未配置密钥'}
              </p>
              <div className="action-cluster" style={{ justifyContent: 'flex-start' }}>
                <label style={{ margin: 0 }}>
                  切换千问模型
                  <select
                    value={picked || llm.data?.llm_model || q.data.model || 'qwen-plus'}
                    disabled={!llm.data?.switchable || switchModel.isPending}
                    onChange={(e) => setPicked(e.target.value)}
                  >
                    {Array.from(
                      new Set([...(llm.data?.llm_model ? [llm.data.llm_model] : []), ...models]),
                    ).map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="secondary"
                  disabled={!llm.data?.switchable || !picked || switchModel.isPending}
                  onClick={() => switchModel.mutate(picked)}
                >
                  {switchModel.isPending ? '正在保存…' : '保存模型'}
                </button>
              </div>
              {llm.data && !llm.data.switchable && (
                <p className="muted">后端尚未提供 /api/settings/llm，暂只能在 .env 中修改模型。</p>
              )}
              <ErrorNote error={switchModel.error || llm.error} />
              <p>{q.data.message}</p>
              <button
                onClick={() => {
                  setMessage('')
                  test.mutate()
                }}
                disabled={test.isPending}
              >
                {test.isPending ? '正在测试…' : '测试连接'}
              </button>
              <ErrorNote error={test.error} />
              {message && <p role="status">{message}</p>}
            </section>
            <section className="panel">
              <h2>文献来源</h2>
              {Object.entries(q.data.sources).map(([key, value]) => (
                <p key={key}>
                  {key === 'openalex' ? 'OpenAlex' : 'Crossref'}：
                  {value.status === 'ok' ? '可用' : `不可用 · ${value.reason}`}
                </p>
              ))}
            </section>
            <section className="panel">
              <h2>调用用量</h2>
              <p>
                {q.data.usage.calls} 次请求 · 输入 {q.data.usage.input_tokens} tokens · 输出{' '}
                {q.data.usage.output_tokens} tokens
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>提示</th>
                      <th>模型</th>
                      <th>输入 / 输出</th>
                      <th>耗时</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.recent_calls.map((call) => (
                      <tr key={call.id}>
                        <td>{prompts[call.prompt_name] || '研究辅助'}</td>
                        <td>{call.model}</td>
                        <td>
                          {call.input_tokens} / {call.output_tokens}
                        </td>
                        <td>{call.latency_ms} ms</td>
                        <td>{call.status === 'succeeded' ? '成功' : call.error || '失败'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!q.data.recent_calls.length && <p className="muted">暂无模型调用记录</p>}
            </section>
          </>
        )
      )}
    </div>
  )
}
