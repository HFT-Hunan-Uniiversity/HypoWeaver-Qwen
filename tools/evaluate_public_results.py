"""Recompute six public metrics from redacted plans and original cell receipts.

Source passages are not distributed. This tool explicitly does NOT recheck their
content hashes, original-text fidelity, or rerun the online model.
"""
from pathlib import Path
import json
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/experiments'))
from evaluate_ai_scientist_system_capability_v2 import canonical_sha256, plan_text, topic_fidelity, wilson

FIELDS=['cell_completed','final_consistency_passed','topic_fidelity','readiness_blocked_correctly','diversity_gate_passed','safe_stop']

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def evaluate(protocol_path, directory):
    protocol=read(protocol_path)
    protocol_hash=canonical_sha256(protocol)
    expected=read(directory/'evaluation.json')
    saved={x['cell_id']:x for x in expected['cells']}
    ablation=read(directory/'retrieval_ablation.json')
    rows=[]
    for case in protocol['cases']:
        for seed in protocol['generation']['seeds']:
            cell_id=f"{case['case_id']}__seed_{seed}"
            cell=directory/'cells'/cell_id
            result=read(cell/'result.json')
            if result['protocol_sha256']!=protocol_hash:
                raise ValueError(f'Protocol mismatch: {cell_id}')
            completed=result['status']=='completed'
            if completed:
                gen=read(cell/'generation_public.json')
                if not gen['submission_projection']['restricted_evidence_text_omitted']:
                    raise ValueError('Expected labelled public projection')
                faithful,_=topic_fidelity(plan_text(gen['plan']),case['concept_groups'])
                readiness=gen.get('execution_readiness') or {}
                diag=gen['evidence_bundle'].get('retrieval_diagnostics') or {}
                hits=gen['evidence_bundle'].get('evidence_hits') or []
                counts=Counter(x['document_id'] for x in hits)
                recorded_diversity=bool(diag.get('diversity_gate_passed'))
                # The original evaluator uses recorded diagnostics; independently
                # check that a positive verdict has the declared supporting IDs.
                if diag.get('diversity_mode')=='per_document_cap' and recorded_diversity and (len(counts)<3 or max(counts.values(),default=0)>2):
                    raise ValueError(f'Diversity IDs contradict positive verdict: {cell_id}')
                row={'cell_completed':True,'final_consistency_passed':bool(gen.get('final_consistency_passed')),
                     'topic_fidelity':faithful,'readiness_blocked_correctly':not bool(readiness.get('can_execute')) and bool(readiness.get('blockers')),
                     'diversity_gate_passed':recorded_diversity,'safe_stop':bool(result.get('safe_stop')) and not bool((result.get('launch') or {}).get('scientific_approval'))}
            elif result['status']=='failed':
                mode=protocol.get('retrieval',{}).get('diversity_mode','per_document_cap')
                diag=ablation[case['case_id']][mode].get('diagnostics') or {}
                row={k:False for k in FIELDS}
                row.update(diversity_gate_passed=bool(diag.get('diversity_gate_passed')),safe_stop=True)
            else:
                raise ValueError(f'Incomplete cell: {cell_id}')
            for k,v in row.items():
                if v != bool(saved[cell_id][k]):
                    raise ValueError(f'Metric mismatch: {cell_id}: {k}')
            rows.append({'cell_id':cell_id,**row})
    metrics={k:wilson(sum(bool(row[k]) for row in rows),len(rows)) for k in FIELDS}
    for k,v in metrics.items():
        if v != expected['metrics_wilson_95'][k]:
            raise ValueError(f'Aggregate mismatch: {k}')
    return {'cells':len(rows),'all_six_metrics_match':True,'metrics':metrics,
            'source_text_integrity':'NOT_RECHECKED_RESTRICTED_TEXT_NOT_DISTRIBUTED','rows':rows}

def main():
    results={}
    for v in ['v2','v3']:
        results[v]=evaluate(ROOT/f'experiments/ai_scientist_system_capability_{v}_protocol.json',ROOT/f'output/experiments/ai_scientist_system_capability_{v}')
    campaign=read(ROOT/'experiments/ai_scientist_component_ablation_20260905_protocol.json')
    for arm in campaign['arms']:
        base=ROOT/'output/experiments/ai_scientist_component_ablation_20260905'/arm
        results[arm]=evaluate(base/'frozen_protocol.json',base)
    out=ROOT/'reproduced/public_metrics.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{'cells':v['cells'],'six_metrics_match':v['all_six_metrics_match']} for k,v in results.items()},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
