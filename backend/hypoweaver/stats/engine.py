from ..errors import AppError
from .models import AnalysisSpec
from .estimation import estimate, event_study
from .permutation import permutation
from .preparation import robustness_spec


def run_analysis(spec, frame, on_step=None, progress=None):
    spec = AnalysisSpec.model_validate(spec) if isinstance(spec, dict) else spec
    steps = {}
    result = {'main': None, 'event': None, 'robustness': [], 'permutation': None, 'sample_report': {}, 'warnings': [], 'steps': steps}

    def step(name, status, error=None):
        steps[name] = {'status': status, 'error': error}
        if on_step:
            on_step(name, status, error)

    step('main', 'running')
    try:
        main, sample, notes = estimate(spec, frame)
        result.update(main=main, sample_report=sample, warnings=notes)
        step('main', 'succeeded')
    except AppError as exc:
        step('main', 'failed', exc.message)
        raise
    if spec.method_family == 'policy_causal':
        step('event_study', 'running')
        try:
            result['event'] = event_study(spec, frame)
            step('event_study', 'succeeded')
        except AppError as exc:
            step('event_study', 'failed', exc.message)
            result['warnings'].append(exc.message)
        result['warnings'].append('错位处理下的双向固定效应可能混合异质效应；本检验本身不保证因果识别。')
    else:
        step('event_study', 'not_applicable', '此方法类别不执行政策事件研究')
    if spec.method_family == 'mechanism_boundary':
        result['warnings'].append('机制回归或交互项仅作机制/边界线索，不代表已识别的中介机制。')
    step('robustness', 'running')
    for check in spec.robustness:
        if progress:
            progress('正在执行稳健性检查：'+check.change)
        try:
            changed, subset = robustness_spec(spec, check, frame)
            estimate_, _, notes = estimate(changed, subset)
            result['robustness'].append({'id': check.id, 'change': check.change, 'kind': check.kind, 'status': 'succeeded', **estimate_})
            result['warnings'].extend(notes)
        except AppError as exc:
            result['robustness'].append({'id': check.id, 'change': check.change, 'kind': check.kind, 'status': 'failed', 'error': exc.message})
    failures = sum(r['status'] == 'failed' for r in result['robustness'])
    step('robustness', 'failed' if failures else 'succeeded', f'{failures} 项检查失败，请查看明细' if failures else None)
    step('permutation', 'running')
    try:
        result['permutation'] = permutation(spec, frame, progress)
        step('permutation', 'succeeded')
    except AppError as exc:
        step('permutation', 'failed', exc.message)
        result['warnings'].append(exc.message)
    return result
