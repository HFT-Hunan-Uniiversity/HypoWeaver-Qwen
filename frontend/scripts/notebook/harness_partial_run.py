"""【harness】模拟：overall succeeded + 主模型成功 + 稳健性一步失败 + 事件研究 N/A → 提案可进。非真实 LLM。"""
import asyncio, json, sys
from playwright.async_api import async_playwright

BASE = "http://localhost:5193"
PID = "pr_0ba00b5bb3ba480c9c654a129ab92bd6"
PLAN = "plan_bc831a1d8a904cca99b0fc7734ca0989"
SH = sys.argv[1] if len(sys.argv) > 1 else None


def overview_payload(orig):
    for s in orig.get("stages") or []:
        if s["key"] == "data":
            s["status"] = "failed"
            s["summary"] = "主模型成功；稳健性有失败"
        if s["key"] == "proposal":
            s["status"] = "not_started"
    return orig


def runs_payload():
    return [
        {
            "id": "run_harness_partial",
            "plan_id": PLAN,
            "dataset_id": "ds_x",
            "status": "succeeded",
            "stale": False,
            "created_at": "2026-10-15T00:00:00Z",
            "job_id": "job_x",
            "error": None,
            "steps": {
                "main": {"status": "succeeded", "error": None},
                "event_study": {
                    "status": "not_applicable",
                    "error": "此方法类别不执行事件研究",
                },
                "robustness": {"status": "failed", "error": "某一稳健性设定失败"},
                "permutation": {"status": "succeeded", "error": None},
                "reproduction": {"status": "succeeded", "error": None},
                "assessment": {"status": "succeeded", "error": None},
            },
            "result": {
                "main": {
                    "coef": 0.07,
                    "se": 0.02,
                    "p": 0.001,
                    "ci": [0.03, 0.11],
                    "n_obs": 1000,
                    "n_units": 100,
                    "r2_within": 0.2,
                    "target": "main",
                },
                "event": None,
                "robustness": [
                    {
                        "id": "r1",
                        "change": "换聚类",
                        "status": "failed",
                        "error": "某一稳健性设定失败",
                    }
                ],
                "permutation": None,
                "sample_report": {
                    "input_rows": 1000,
                    "n_valid": 1000,
                    "dropped_by_reason": {
                        "sample_filters": 0,
                        "missing_or_nonfinite": 0,
                    },
                    "n_clusters": 10,
                },
                "warnings": [],
            },
            "plan_snapshot": {
                "version": 2,
                "method_family": "did",
                "boundary_notes": "",
            },
            "spec": {
                "cluster": "unit",
                "controls": [],
                "outcome": "y",
                "treatment": "d",
            },
            "reproduction": None,
        }
    ]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 720})

        async def ov(route):
            r = await route.fetch()
            body = await r.json()
            await route.fulfill(json=overview_payload(body))

        async def runs(route):
            await route.fulfill(json=runs_payload())

        await pg.route(f"**/api/projects/{PID}/overview", ov)
        await pg.route(f"**/api/projects/{PID}/runs", runs)
        await pg.goto(f"{BASE}/")
        await pg.evaluate(
            f"localStorage.setItem('hw.flow.{PID}', JSON.stringify({{confirmed:{{direction:1,literature:1,candidates:1,plan:1}},editing:{{}},stale:{{}}}}))"
        )
        await pg.goto(f"{BASE}/p/{PID}/data?tab=results")
        # wait until proposal unlocked (runs loaded → dataRunOk)
        for _ in range(40):
            ok = await pg.evaluate(
                """() => {
              const prop=[...document.querySelectorAll('.wz-sp')].find(b=>/研究提案/.test(b.innerText));
              const prim=document.querySelector('.wz-card [data-primary]')?.innerText || '';
              return prop && !prop.disabled && /确认并进入下一阶段|生成/.test(prim);
            }"""
            )
            if ok:
                break
            await pg.wait_for_timeout(250)
        # expand process timeline to assert N/A row styling
        await pg.evaluate("""() => {
          const sum=document.querySelector('.ptl__summary');
          if (sum && !document.querySelector('.ptl.is-open')) sum.click();
        }""")
        await pg.wait_for_timeout(300)
        info = await pg.evaluate(
            """() => {
          const steps=[...document.querySelectorAll('.ptl__row')].map(r=>({
            cls: r.className, text: r.innerText.replace(/\\s+/g,' ').slice(0,60)}));
          const errs=[...document.querySelectorAll('.error')].map(e=>e.innerText.slice(0,80));
          const muted=[...document.querySelectorAll('.muted')].map(e=>e.innerText).filter(t=>/不适用|不执行/.test(t));
          const notice=[...document.querySelectorAll('.notice')].map(e=>e.innerText.slice(0,100));
          const summary=document.querySelector('.ptl__summary')?.innerText || '';
          const prim=document.querySelector('.wz-card [data-primary]')?.innerText;
          const primDisabled=document.querySelector('.wz-card [data-primary]')?.disabled;
          const badge=document.querySelector('.wz-badge')?.innerText;
          const propBtn=[...document.querySelectorAll('.wz-sp')].find(b=>/研究提案/.test(b.innerText));
          return {steps,errs,muted,notice,summary,prim,primDisabled,badge,
            proposalDisabled: propBtn?.disabled, proposalClass: propBtn?.className};
        }"""
        )
        print("data page:", json.dumps(info, ensure_ascii=False)[:1200])
        if SH:
            await pg.screenshot(path=f"{SH}/partial_data.png", full_page=True)

        await pg.goto(f"{BASE}/p/{PID}/proposal")
        for _ in range(60):
            ready = await pg.evaluate(
                """() => {
              const title=document.querySelector('.wz-card h2')?.innerText || '';
              const prim=document.querySelector('.wz-card [data-primary]')?.innerText || '';
              return /提案/.test(title) && /生成|去设置模型/.test(prim);
            }"""
            )
            if ready:
                break
            await pg.wait_for_timeout(250)
        prop = await pg.evaluate(
            """() => ({
          url: location.pathname,
          title: document.querySelector('.wz-card h2')?.innerText,
          locked: !!document.querySelector('.wz-sp.is-locked.is-on'),
          prim: document.querySelector('.wz-card [data-primary]')?.innerText,
          primDisabled: !!document.querySelector('.wz-card [data-primary]')?.disabled,
          body: (document.querySelector('.wz-card')?.innerText || '').slice(0,160)
        })"""
        )
        print("proposal page:", json.dumps(prop, ensure_ascii=False))
        na_ok = any("is-na" in s["cls"] for s in info["steps"])
        na_not_red = not any(
            "事件研究" in e or "不执行" in e for e in info["errs"]
        )
        no_fake_progress = "进行中" not in info["summary"]
        confirm_ok = info["prim"] and "确认并进入下一阶段" in info["prim"] and not info["primDisabled"]
        prop_ok = (
            prop.get("title")
            and "提案" in prop["title"]
            and "/proposal" in (prop.get("url") or "")
            and not prop.get("locked")
            and prop.get("prim")
            and (("生成" in prop["prim"]) or ("去设置模型" in prop["prim"]))
            and not prop.get("primDisabled")
        )
        print(
            "checks:",
            json.dumps(
                {
                    "na_ok": na_ok,
                    "na_not_red": na_not_red,
                    "no_fake_progress": no_fake_progress,
                    "confirm_ok": confirm_ok,
                    "prop_ok": prop_ok,
                    "badge": info.get("badge"),
                },
                ensure_ascii=False,
            ),
        )
        ok = na_ok and na_not_red and no_fake_progress and confirm_ok and prop_ok
        print("PASS" if ok else "FAIL")
        if SH:
            await pg.screenshot(path=f"{SH}/partial_proposal.png", full_page=True)
        await b.close()
        sys.exit(0 if ok else 1)


asyncio.run(main())
