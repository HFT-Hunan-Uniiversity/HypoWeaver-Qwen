"""把旧仓库的真实案例（碳市场、Case009）导入为只读项目。

用法：python scripts/import_legacy_cases.py [--db 路径]
默认数据库：$DATA_DIR/hypoweaver.sqlite（未设置时为 var/hypoweaver.sqlite）。
可重复执行：先删除同 case 的旧导入，再重建。导入前自动 sqlite .backup 备份。
正文与数字原样取自 docs/legacy_cases/*.md，不做改写。
"""
import argparse, json, os, re, sqlite3, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["problem", "rationale", "techniques", "datasets", "title",
        "abstract", "methods", "experiments", "results", "references"]

CARBON_TABLES_DATA = """

### 表1  主要变量定义

| 变量 | 符号 | 定义 | 预期方向 | 数据来源 |
|---|---|---|---|---|
| 高质量绿色创新 | LnGreenInv | ln（1＋绿色发明专利独立申请＋联合申请） | — | 公开数据中的绿色专利字段 |
| 碳政策暴露 | Exposure | 数据发布者提供的企业—年份碳政策暴露编码 | ＋ | Mendeley Data原数据 |
| 企业规模 | Size | 企业总资产的自然对数 | 待定 | 公开企业财务字段 |
| 资产负债率 | Lev | 总负债与总资产之比 | 待定 | 公开企业财务字段 |
| 资产收益率 | ROA | 企业资产收益率 | ＋ | 公开企业财务字段 |
| 融资约束 | AbsSA | SA融资约束指数的绝对值 | － | 公开企业财务字段 |
| 行业集中度 | HHI | 企业所在行业年度HHI | 待定 | 公开行业竞争字段 |

注：Exposure为公开数据发布者提供的源定义编码，未改写为全国碳市场官方履约名单；变量口径、样本规则和估计方法均在读取结果前冻结。

### 表2  主要变量的描述性统计

| 变量 | 观测值 | 均值 | 标准差 | 最小值 | 最大值 |
|---|---:|---:|---:|---:|---:|
| LnGreenInv | 14196 | 0.3880 | 0.9084 | 0.0000 | 7.2598 |
| Exposure | 14196 | 0.4801 | 0.4996 | 0.0000 | 1.0000 |
| Size | 14196 | 6.4763 | 1.3281 | 3.0263 | 12.5184 |
| Lev | 14196 | 0.4603 | 0.1956 | 0.0080 | 1.0564 |
| ROA | 14196 | 0.0393 | 0.0559 | −0.9652 | 0.5262 |
| AbsSA | 14196 | 3.8153 | 0.2742 | 2.1196 | 4.7566 |

注：主样本为2010—2021年12期齐全且主结果、政策暴露和三项控制变量无缺失的企业平衡面板；主模型不因显著性剔除样本，也不事后缩尾。
"""

CARBON_FIG1 = """

![图1  碳市场影响企业高质量绿色创新的理论机制](/cases/carbon/figure_1_mechanism.png)

图1  碳市场影响企业高质量绿色创新的理论机制。注：该图为理论框架，不是统计估计结果。融资约束与市场竞争分别作为机制一致性和探索性异质性诊断。
"""

CARBON_FIGS = """
![图2  政策暴露前后的绿色发明专利动态](/cases/carbon/figure_2_event_study.png)

图2  政策暴露前后的绿色发明专利动态。注：点为企业和年份固定效应估计，线段为企业层面聚类的95%置信区间；−1期为基期。仅使用政策路径单调的企业，作为趋势与动态模式诊断。数据来源：Mendeley Data公开复现样本（CC BY 4.0）。

![图3  不同模型设定下的政策暴露系数](/cases/carbon/figure_3_robustness.png)

图3  不同模型设定下的政策暴露系数。注：点为估计系数，横线为企业层面聚类的95%置信区间。不同结果变量用于稳健性和创新质量区分，不比较系数绝对大小。

"""

CASES = [
    {
        "case": "legacy:carbon",
        "file": "docs/legacy_cases/carbon.md",
        "title": "碳市场约束能否转化为企业高质量绿色创新？",
        "direction": {
            "text": "研究全国碳排放权交易市场能否促进企业高质量绿色技术创新；本轮在公开数据下收敛为区域碳政策公开复现。",
            "question": "碳市场约束能否转化为企业高质量绿色创新？",
            "constraints": ["中国上市公司", "2010—2021", "绿色发明专利"],
            "domain": "环境经济学/创新经济学",
        },
        "age_days": 1,
    },
    {
        "case": "legacy:case009",
        "file": "docs/legacy_cases/case009.md",
        "title": "绿色金融试验区能否改善城市空气质量？（Case009）",
        "direction": {
            "text": "复核绿色金融改革创新试验区（GFRI）对城市空气质量指数（AQI）的影响，并检验其是否达到因果结论准入标准。",
            "question": "GFRI 能否改善城市空气质量？",
            "constraints": ["中国地级市", "城市—月度面板", "AQI"],
            "domain": "绿色金融/环境经济学",
        },
        "age_days": 2,
    },
]


def latex(text):
    text = re.sub(r"\\\[\s*([\s\S]*?)\s*\\\]", lambda m: "```text\n" + m.group(1).strip() + "\n```", text)
    return re.sub(r"\\\((.+?)\\\)", lambda m: "`" + m.group(1) + "`", text)


def split(md):
    head, *parts = re.split(r"^## ", md, flags=re.M)
    sections = []
    for part in parts:
        title, _, body = part.partition("\n")
        sections.append((title.strip(), body.strip()))
    return head, sections


def build(case):
    head, sections = split((ROOT / case["file"]).read_text(encoding="utf-8"))
    ten, extra = sections[:10], sections[10:]
    lead = "\n".join(l for l in head.splitlines() if l.startswith(">")).strip()
    out = {}
    for key, (_, body) in zip(KEYS, ten):
        out[key] = body
    out["problem"] = lead + "\n\n" + out["problem"]
    for title, body in extra:  # 「推荐放入…的结果卡」并入实验结果
        out["results"] += f"\n\n### {title}\n\n{body}"
    if case["case"] == "legacy:carbon":
        out["rationale"] += CARBON_FIG1
        out["datasets"] += CARBON_TABLES_DATA
        out["results"] = out["results"].replace("### 9.4", CARBON_FIGS + "### 9.4", 1)
    return [
        {"key": k, "markdown": latex(out[k]), "injected_numbers_ref": {}, "editable": False,
         "source_ref": {"legacy_file": case["file"]}}
        for k in KEYS
    ]


def main():
    ap = argparse.ArgumentParser()
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "var"))
    ap.add_argument("--db", default=str(data_dir / "hypoweaver.sqlite"))
    db_path = Path(ap.parse_args().db)
    con = sqlite3.connect(db_path)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = db_path.with_name(f"backup_pre_legacy_import_{stamp}.sqlite")
    bcon = sqlite3.connect(backup)
    con.backup(bcon)
    bcon.close()
    print("backup:", backup)
    con.execute("PRAGMA foreign_keys=ON")
    for case in CASES:
        for (pid,) in con.execute("select id from projects where \"case\"=?", (case["case"],)).fetchall():
            con.execute("delete from proposals where project_id=?", (pid,))
            con.execute("delete from projects where id=?", (pid,))
        ts = (datetime.now(timezone.utc) - timedelta(days=case["age_days"])).isoformat()
        pid = "pr_" + uuid.uuid4().hex
        con.execute(
            "insert into projects (id,title,direction,selected_candidate_id,created_at,updated_at,\"case\") values (?,?,?,?,?,?,?)",
            (pid, case["title"], json.dumps(case["direction"], ensure_ascii=False), None, ts, ts, case["case"]),
        )
        snapshot = {"project": {"id": pid, "title": case["title"], "case": case["case"], "direction": case["direction"]},
                    "candidate": None, "plan": None, "run": None, "binding": None, "dataset": None,
                    "claims": [], "evidence": [], "readiness": {}, "legacy_source": case["file"]}
        con.execute(
            "insert into proposals (id,project_id,llm_model,interpretation,narrative_status,narrative_errors,version,kind,sections,snapshot,removed_references,stale,created_at)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("proposal_" + uuid.uuid4().hex, pid, None, None, "complete", json.dumps([]), 1, "empirical",
             json.dumps(build(case), ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False), 0, 0, ts),
        )
        print("imported", case["case"], pid)
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
