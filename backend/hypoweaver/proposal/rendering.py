import re
from ..claims.service import check_wording

TITLES={'overview':'一页概览','question':'研究问题与贡献','literature':'文献依据','gap':'研究缺口','hypothesis':'假设与机制','design':'识别设计','data':'数据与变量','results':'探索性结果','conclusions':'结论与边界','limitations':'局限和后续计划','references':'参考文献'}
NARRATIVE=[k for k in TITLES if k not in {'results','conclusions','references'}]
TOKEN=re.compile(r'\{\{num:([a-zA-Z0-9_.]+)\}\}')


def number(value):
    if value is None:return '未估计'
    if isinstance(value,int):return str(value)
    return format(value,'.6g')


def issues(text,numbers,strength):
    bad=[]
    if any(k not in numbers for k in TOKEN.findall(text)):
        bad.append('存在未知数字占位符')
    stripped=TOKEN.sub('',text)
    chinese_number = r'(?:百分之|千分之|万分之|[零〇一二两三四五六七八九十百千万亿数几半]+点[零〇一二三四五六七八九]+|[零〇一二两三四五六七八九十百千万亿数几]*[十百千万亿][零〇一二两三四五六七八九十百千万亿]*|[零〇一二两三四五六七八九半数几]+(?:家|名|个|条|行|次|期|年|月|日|倍|成|项|个百分点))'
    english_number = r'\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion)\b'
    if re.search(r'\d',stripped) or re.search(chinese_number,stripped) or re.search(english_number,stripped,re.I):
        bad.append('所有数字须使用给定占位符')
    if not check_wording(stripped,strength)['valid']:
        bad.append('存在超出结论上限的措辞')
    return bad


def inject(text,numbers):
    return TOKEN.sub(lambda m:number(numbers[m.group(1)]),text)


def render_markdown(proposal):
    parts=['# '+proposal.snapshot['project']['title'], '计划型提案（尚无实证结果）' if proposal.kind=='plan_only' else '含探索性结果的研究提案']
    if proposal.stale:parts.append('> 上游信息已变更，本提案已过期。')
    for section in proposal.sections:
        parts += ['## '+TITLES[section['key']],inject(section['markdown'],section['injected_numbers_ref'])]
    return '\n\n'.join(parts)+'\n'


def result_table(result,numbers):
    if not result:return '尚无实证结果。需补齐变量、确认绑定并完成统计检验。'
    header='| 检验 | 系数 | 标准误 | p 值 | 观测数 |\n|---|---:|---:|---:|---:|'
    rows=[]
    for i,r in enumerate([result['main'],*result['robustness']]):
        if r.get('status','succeeded')!='succeeded':
            rows.append(f"| {r['change']} | 失败 | — | — | — |")
            continue
        prefix='main' if i==0 else f'robust{i}'
        for k in ['coef','se','p','n_obs']:numbers[prefix+'.'+k]=r[k]
        label='主模型' if i==0 else r['change']
        rows.append('| '+label+' | '+' | '.join('{{num:'+prefix+'.'+k+'}}' for k in ['coef','se','p','n_obs'])+' |')
    diagnostic=[]
    if result.get('event'):
        numbers['event.pretrend_p']=result['event']['pretrend_wald']['p']
        diagnostic.append('前趋势联合检验 p={{num:event.pretrend_p}}。')
    if result.get('permutation'):
        numbers['permutation.p']=result['permutation']['p'];numbers['permutation.n']=result['permutation']['n']
        diagnostic.append('置换 {{num:permutation.n}} 次，双侧 p={{num:permutation.p}}。')
    return header+'\n'+'\n'.join(rows)+'\n\n'+' '.join(diagnostic)
