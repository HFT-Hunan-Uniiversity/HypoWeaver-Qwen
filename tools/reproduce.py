"""Offline re-evaluation or independent statistics in a separate bounded directory."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/experiments'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('task',choices=['metrics','case009','case010','qwen-vl','readiness'])
    args=parser.parse_args()
    os.chdir(ROOT)
    if args.task=='metrics':
        runpy.run_path(str(ROOT/'tools/evaluate_public_results.py'),run_name='__main__')
        return
    base=ROOT/'reproduced'/args.task
    base.mkdir(parents=True,exist_ok=True)
    if args.task=='case009':
        source=ROOT/'output/experiments/track1b_case009_two_round_v1'
        for name in ['round1_result.json','round2_result.json']:
            shutil.copy2(source/name,base/name)
        sys.argv=['verify_track1b_case009_two_round.py','--data',str(ROOT/'experiments/fixtures/case009_harvard_dataverse_data_v1.xlsx'),'--output-dir',str(base)]
        runpy.run_path(str(ROOT/'scripts/experiments/verify_track1b_case009_two_round.py'),run_name='__main__')
    elif args.task=='case010':
        import verify_case010_carbon_market_adaptive as v
        # Keep frozen results read-only; redirect only the verifier output while
        # retaining the original data and result hash checks in the verifier.
        v.OUTPUT_DIR=base
        source=ROOT/'output/experiments/case010_carbon_market_adaptive_v1'
        for name in ['round1_result.json','round2_result.json','placebo_distribution.csv','model_comparison.csv','event_study.csv','mechanism_and_heterogeneity.csv','figure_manifest.json']:
            shutil.copy2(source/name,base/name)
        v.ROUND1_RESULT=base/'round1_result.json'
        v.ROUND2_RESULT=base/'round2_result.json'
        v.main()
    elif args.task=='readiness':
        public_generation=ROOT/'output/experiments/ai_scientist_system_capability_v2/cells/Q01_green_patent_quality__seed_20260901/generation_public.json'
        sys.argv=['run_execution_readiness_contract_control_v1.py','--generation',str(public_generation),'--output',str(base/'result.json')]
        runpy.run_path(str(ROOT/'scripts/experiments/run_execution_readiness_contract_control_v1.py'),run_name='__main__')
    else:
        from evaluate_qwen_vl_table_experiment import evaluate
        d=ROOT/'output/experiments/qwen_vl_scientific_table'
        truth=json.loads((d/'ground_truth.json').read_text(encoding='utf-8'))
        rows=[]
        for p in sorted((d/'qwen_runs').glob('extraction_*.json')):
            result=evaluate(truth,json.loads(p.read_text(encoding='utf-8')),0.0005)
            rows.append({'file':p.name,'evaluation':result})
        if len(rows)!=6:
            raise ValueError(f'Expected six formal Qwen-VL extractions, found {len(rows)}')
        (base/'evaluation.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'evaluated_runs':len(rows),'output':'reproduced/qwen-vl/evaluation.json'}))

if __name__=='__main__':
    main()
