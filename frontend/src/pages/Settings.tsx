import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { QWEN_MODELS, useLlm } from '../lib/llm'
import { getBrowserKey, setBrowserKey, setBrowserModel } from '../lib/llmKey'
interface Status {
  configured: boolean
  /** R4-03 起的字段名 */
  llm_model?: string | null
  /** 旧后端字段，兼容保留 */
  model?: string | null
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
  const [keyDraft, setKeyDraft] = useState('')
  const [hasKey, setHasKey] = useState(() => !!getBrowserKey())
  const refresh = () => {
    for (const k of ['llm', 'settings']) cache.invalidateQueries({ queryKey: [k] })
  }
  // 模型与密钥都只保存在本浏览器，不修改服务器上的全局设置
  const switchModel = useMutation({
    mutationFn: async (model: string) => setBrowserModel(model),
    onSuccess: () => {
      setPicked('')
      refresh()
    },
  })
  const saveKey = () => {
    setBrowserKey(keyDraft)
    setKeyDraft('')
    setHasKey(!!getBrowserKey())
    setMessage('')
    refresh()
  }
  const clearKey = () => {
    setBrowserKey('')
    setKeyDraft('')
    setHasKey(false)
    setMessage('')
    refresh()
  }
  const models = QWEN_MODELS
  const test = useMutation({
    mutationFn: () => api<{ message: string }>('/settings/llm:test', body('POST')),
    onSuccess: (r) => setMessage(r.message),
    onSettled: () => {
      cache.invalidateQueries({ queryKey: ['settings'] })
    },
  })
  return (
    <section className="wz-card settings-card">
      <header className="wz-card__hd">
        <div className="wz-card__hd-main">
          <h2>服务与用量</h2>
          <p className="wz-card__sub">
            千问密钥只保存在你自己的浏览器里，随请求临时发给服务器使用，服务器不会保存。
          </p>
        </div>
      </header>
      <div className="stage-body">
        <ErrorNote error={q.error} />
        {q.isPending ? (
          <p className="loading-line">正在检查服务状态…</p>
        ) : (
          q.data && (
            <div className="settings-grid">
              <div className="settings-left">
                <section className="panel settings-panel">
                  <h2>模型连接 · 千问</h2>
                  <p>
                    当前模型：
                    <strong>
                      {llm.data?.llm_model ||
                        q.data.llm_model ||
                        q.data.model ||
                        '未设置（默认 qwen-plus）'}
                    </strong>{' '}
                    ·{' '}
                    {hasKey
                      ? '已配置（本浏览器密钥）'
                      : (llm.data?.configured ?? q.data.configured)
                        ? '已配置（服务器本机密钥）'
                        : '未配置密钥'}
                  </p>
                  <div className="action-cluster" style={{ justifyContent: 'flex-start' }}>
                    <label style={{ margin: 0 }}>
                      千问 API Key（只存本浏览器）
                      <input
                        type="password"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder={hasKey ? '已保存，输入新密钥可替换' : 'sk-…'}
                        value={keyDraft}
                        onChange={(e) => setKeyDraft(e.target.value)}
                      />
                    </label>
                    <button className="secondary" disabled={!keyDraft.trim()} onClick={saveKey}>
                      保存到本浏览器
                    </button>
                    {hasKey && (
                      <button className="secondary" onClick={clearKey}>
                        清除密钥
                      </button>
                    )}
                  </div>
                  <div className="action-cluster" style={{ justifyContent: 'flex-start' }}>
                    <label style={{ margin: 0 }}>
                      切换千问模型
                      <select
                        value={
                          picked ||
                          llm.data?.llm_model ||
                          q.data.llm_model ||
                          q.data.model ||
                          'qwen-plus'
                        }
                        disabled={!llm.data?.switchable || switchModel.isPending}
                        onChange={(e) => setPicked(e.target.value)}
                      >
                        {Array.from(
                          new Set([
                            ...(llm.data?.llm_model ? [llm.data.llm_model] : []),
                            ...models,
                          ]),
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
                      {switchModel.isPending ? '正在保存…' : '保存模型（本浏览器）'}
                    </button>
                  </div>
                  {llm.data && !llm.data.switchable && (
                    <p className="muted">
                      后端尚未提供 /api/settings/llm，暂只能在 .env 中修改模型。
                    </p>
                  )}
                  <ErrorNote error={switchModel.error || llm.error} />
                  <p>{q.data.message}</p>
                  <div className="settings-test-row">
                    <button
                      onClick={() => {
                        setMessage('')
                        test.mutate()
                      }}
                      disabled={test.isPending}
                    >
                      {test.isPending ? '正在测试…' : '测试连接'}
                    </button>
                    {message && (
                      <span role="status" className="settings-test-msg">
                        {message}
                      </span>
                    )}
                  </div>
                  <ErrorNote error={test.error} />
                </section>
                <section className="panel settings-panel settings-sources-panel">
                  <h2>文献来源</h2>
                  <div className="settings-sources-list">
                    {Object.entries(q.data.sources).map(([key, value]) => (
                      <div key={key} className="settings-source-row">
                        <span className="settings-source-name">
                          {key === 'openalex' ? 'OpenAlex' : 'Crossref'}
                        </span>
                        <span
                          className={
                            'settings-status-pill ' + (value.status === 'ok' ? 'is-ok' : 'is-err')
                          }
                        >
                          {value.status === 'ok' ? '可用' : `不可用 · ${value.reason}`}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
              <section className="panel settings-panel settings-calls-panel">
                <div className="settings-calls-hd">
                  <h2>调用用量</h2>
                  <p className="settings-calls-summary">
                    <b>{q.data.usage.calls}</b> 次请求 · 输入{' '}
                    <b>{q.data.usage.input_tokens.toLocaleString()}</b> tokens · 输出{' '}
                    <b>{q.data.usage.output_tokens.toLocaleString()}</b> tokens
                  </p>
                </div>
                <div className="settings-calls-scroll" role="region" aria-label="最近调用">
                  <table className="settings-calls-table">
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
                          <td>
                            {call.status === 'succeeded' ? (
                              <span className="settings-status-pill is-ok">成功</span>
                            ) : (
                              <span
                                className="settings-status-pill is-err"
                                title={call.error || '调用失败'}
                              >
                                失败
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!q.data.recent_calls.length && <p className="muted">暂无模型调用记录</p>}
              </section>
            </div>
          )
        )}
      </div>
    </section>
  )
}
