import re
from collections import Counter
from itertools import combinations
from ..db import now

METHODS = {
    "DID": r"\bDID\b|difference[ -]in[ -]differences|双重差分|双重差分法",
    "事件研究": r"event.study|事件研究",
    "中介分析": r"mediat(?:ion|ing)|中介",
    "工具变量": r"instrumental.variable|工具变量",
    "门槛模型": r"threshold.model|门槛",
    "固定效应": r"fixed.effect|固定效应",
}
CHINESE_TERMS = ["碳市场", "碳交易", "碳排放", "绿色创新", "绿色金融", "绿色信贷", "绿色专利", "企业创新", "融资约束", "数字化", "环境规制", "产业结构", "政策试点", "同群效应", "技术创新", "全要素生产率"]
STOPWORDS = set("the and for with from that this are its using how does what under between through green study evidence effect impact corporate innovation carbon market markets china research analysis based policy firms enterprise enterprises an of in on to a as by at is or be their can do we which have not".split())


def keywords(card):
    concepts = {str(c).strip().lower() for c in card.get("concepts", []) if str(c).strip()}
    title = card.get("title", "").lower()
    concepts.update(term for term in CHINESE_TERMS if term in title)
    if not card.get("concepts"):
        concepts.update(word for word in re.findall(r"[a-z][a-z-]{3,}", title) if word not in STOPWORDS)
    return sorted(concepts)


def build_landscape(cards):
    cards = [c for c in cards if c.get("included", True)]
    years = Counter(c["year"] for c in cards if c.get("year"))
    venues = Counter(c["venue"] for c in cards if c.get("venue"))
    term_sets = [keywords(c) for c in cards]
    terms = Counter(term for ts in term_sets for term in ts)
    top = dict(terms.most_common(18))
    edges = Counter(pair for ts in term_sets for pair in combinations(sorted(set(ts)&set(top)), 2))
    methods = {name:sum(bool(re.search(pattern, c.get("title", "")+' '+(c.get("abstract") or '')+' '+(c.get("fulltext_excerpt") or ''), re.I)) for c in cards) for name,pattern in METHODS.items()}
    return {"computed_at":now(), "sample_label":"基于本次检索样本", "n_cards":len(cards),
            "unknown_year":sum(not c.get("year") for c in cards),
            "years":[{"year":year,"count":count} for year,count in sorted(years.items())],
            "venues":[{"name":name,"count":count} for name,count in venues.most_common(10)],
            "keywords":[{"name":name,"count":count} for name,count in top.items()],
            "edges":[{"source":a,"target":b,"count":n} for (a,b),n in edges.most_common(50)],
            "methods":[{"name":name,"count":count} for name,count in methods.items()],
            "top_cited":[{"id":c['id'],"title":c['title'],"cited_by":c.get('cited_by') or 0} for c in sorted(cards,key=lambda c:c.get('cited_by') or 0,reverse=True)[:5]]}
