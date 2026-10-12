import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { ErrorNote } from './Shared'
import { GeneratedBy } from './ui/Bits'
export const strengths: Record<string, string> = {
  insufficient: '证据不足',
  preliminary: '初步线索',
  mixed: '混合证据',
  associational: '关联',
  causal_cautious: '谨慎因果',
}
const verdicts: Record<string, string> = {
  supportive: '支持',
  mixed: '混合',
  not_supportive: '不支持',
  insufficient: '证据不足',
}
type Claim = {
  run_id: string
  claim_id: string
  verdict: string
  max_strength: string
  allowed_wording: string
  blockers: string[]
  user_decision: string
  chosen_strength: string
  final_text: string
  llm_model?: string | null
}
function Card({ claim }: { claim: Claim }) {
  const qc = useQueryClient(),
    [decision, setDecision] = useState(
      claim.user_decision === 'pending' ? 'accepted' : claim.user_decision,
    ),
    [strength, setStrength] = useState(claim.chosen_strength),
    [text, setText] = useState(claim.final_text)
  const mutation = useMutation({
    mutationFn: () =>
      api(
        `/claims/${claim.run_id}/${claim.claim_id}`,
        body('PATCH', { user_decision: decision, chosen_strength: strength, final_text: text }),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['claims', claim.run_id] })
      qc.invalidateQueries({ queryKey: ['proposals'] })
    },
  })
  const choices = Object.keys(strengths).slice(
    0,
    Object.keys(strengths).indexOf(claim.max_strength) + 1,
  )
  return (
    <article className="panel">
      <h3>
        结论判定：{verdicts[claim.verdict]} <GeneratedBy of={claim} />
      </h3>
      <p>
        <strong>强度上限：{strengths[claim.max_strength]}</strong>
      </p>
      <p>{claim.allowed_wording}</p>
      {claim.blockers.length > 0 && (
        <ul>
          {claim.blockers.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      <label>
        研究者决定
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="accepted">接受</option>
          <option value="downgraded">降级</option>
          <option value="deferred">暂缓</option>
          <option value="rejected">拒绝</option>
        </select>
      </label>
      <label>
        采用强度
        <select value={strength} onChange={(e) => setStrength(e.target.value)}>
          {choices.map((k) => (
            <option key={k} value={k}>
              {strengths[k]}
            </option>
          ))}
        </select>
      </label>
      <label>
        最终叙述
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
      </label>
      <ErrorNote error={mutation.error} />
      <button disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        保存决定
      </button>
      {mutation.isSuccess && <span role="status"> 已保存</span>}
    </article>
  )
}
export default function Claims({ runId }: { runId: string }) {
  const query = useQuery({
    queryKey: ['claims', runId],
    queryFn: () => api<Claim[]>(`/runs/${runId}/claims`),
  })
  return (
    <section>
      <h2>结论评估与研究者决定</h2>
      <ErrorNote error={query.error} />
      {query.data?.map((c) => (
        <Card key={runId + c.claim_id} claim={c} />
      ))}
      {!query.data?.length && <p className="muted">本次运行尚无结论评估。</p>}
    </section>
  )
}
