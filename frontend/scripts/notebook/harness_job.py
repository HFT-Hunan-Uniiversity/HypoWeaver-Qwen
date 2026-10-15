"""【harness，仅界面】拦截路由模拟候选 job 运行→失败。不是真实 LLM。"""
import asyncio, sys, json, datetime
from playwright.async_api import async_playwright
PID, SH = sys.argv[1], sys.argv[2]
state = {'job': 'running', 'posts': 0}
def iso(dt): return dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'
START = iso(datetime.datetime.utcnow() - datetime.timedelta(seconds=37))
def job():
    j = {'id': 'job_harness', 'kind': 'candidates', 'status': state['job'], 'progress_text': '正在生成候选假设…', 'error': None, 'result': None, 'created_at': START, 'started_at': START, 'finished_at': None}
    if state['job'] == 'failed': j.update(error='模型调用超时（240s）', finished_at=iso(datetime.datetime.utcnow()))
    return j
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1280, 'height': 720})
        async def llm(r): await r.fulfill(json={'configured': True, 'llm_model': 'harness'})
        async def post_sets(r):
            if r.request.method == 'POST':
                state['posts'] += 1; state['job'] = 'running'
                await r.fulfill(json={'job_id': 'job_harness'})
            else: await r.continue_()
        async def jobs(r): await r.fulfill(json=job())
        async def jobs_list(r): await r.fulfill(json=[job()] if state['posts'] else [])
        await pg.route('**/api/settings/llm', llm)
        await pg.route(f'**/api/projects/{PID}/candidate-sets', post_sets)
        await pg.route('**/api/jobs/job_harness', jobs)
        await pg.route(f'**/api/projects/{PID}/jobs?kind=candidates', jobs_list)
        await pg.goto('http://localhost:5193/')
        await pg.evaluate("([k, v]) => localStorage.setItem(k, v)", [f'hw.flow.{PID}', json.dumps({'confirmed': {'direction': 1, 'literature': 1}, 'editing': {}, 'stale': {}})])
        await pg.goto(f'http://localhost:5193/p/{PID}/candidates'); await pg.wait_for_timeout(2500)
        await pg.click('.wz-card [data-primary]'); await pg.wait_for_timeout(2500)
        info = await pg.evaluate("() => ({step: document.querySelector('.wz-sp.is-on')?.className, badge: document.querySelector('.wz-badge')?.innerText, job: document.querySelector('.job')?.innerText, primDisabled: document.querySelector('.wz-card [data-primary]')?.disabled})")
        print('running:', json.dumps(info, ensure_ascii=False))
        await pg.screenshot(path=f'{SH}/H01_harness_job_running.png')
        state['job'] = 'failed'; await pg.wait_for_timeout(3000)
        info = await pg.evaluate("() => ({badge: document.querySelector('.wz-badge')?.innerText, job: document.querySelector('.job')?.innerText, prim: document.querySelector('.wz-card [data-primary]')?.innerText})")
        print('failed:', json.dumps(info, ensure_ascii=False))
        await pg.screenshot(path=f'{SH}/H02_harness_job_failed.png')
        print('posts so far (no auto retry):', state['posts'])
        await b.close()
asyncio.run(main())
