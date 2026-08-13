# HypoWeaver-Qwen API 调用指南

本文面向需要从脚本、服务或外部 Agent 调用 HypoWeaver 的开发者。服务启动后，Swagger UI 位于 `/docs`，机器可读 OpenAPI 位于 `/openapi.json`。

## 1. 基本约定

默认地址：

```text
http://127.0.0.1:8000
```

所有业务接口位于 `/api/v1`。JSON 请求使用：

```http
Content-Type: application/json
Accept: application/json
```

### 写接口认证

如果服务设置了 `HYPOWEAVER_API_TOKEN`，每个 POST、PUT、DELETE 请求都必须包含：

```http
X-Hypoweaver-Token: <workflow-token>
```

未设置 token 时，写接口只允许 loopback 请求。浏览器前端把 token 保存在当前标签页的 `sessionStorage`，不会写入构建产物。

Shell 示例统一使用：

```bash
export HW_BASE_URL=http://127.0.0.1:8000
export HW_TOKEN=replace-with-your-token
```

PowerShell：

```powershell
$env:HW_BASE_URL='http://127.0.0.1:8000'
$env:HW_TOKEN='replace-with-your-token'
```

## 2. 健康检查与服务发现

```bash
curl "$HW_BASE_URL/api/v1/health"
curl "$HW_BASE_URL/api/v1/definitions/app-a"
curl "$HW_BASE_URL/openapi.json"
```

健康检查成功示例：

```json
{
  "status": "ok",
  "runtime": "code-native",
  "definition": "app-a@1.8.0"
}
```

外部 Agent 应优先读取 `/openapi.json`，不要把本文中的字段列表硬编码为永不变化的契约。

## 3. 最小 Fixture 全流程

Fixture 用于验证工作流和人工闸门，不生成可用于实证论文的结论。

### 3.1 创建 run

```bash
curl -X POST "$HW_BASE_URL/api/v1/runs" \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  -d '{
    "preset_case_id": "green-finance-did",
    "mode": "fixture",
    "model_provider": "fixture",
    "execution_mode": "fixture"
  }'
```

响应是完整 `RunState`。保存以下字段：

- `id`：后续 URL 使用的 run id；
- `version`：乐观并发控制版本；
- `status`；
- `current_gate`；
- `claims`：H3 逐条决定所需的 claim id。

### 3.2 H1/H2/H4 批准

每次决定前先重新 GET run，使用最新 `version`：

```bash
curl "$HW_BASE_URL/api/v1/runs/$RUN_ID"
```

```bash
curl -X POST "$HW_BASE_URL/api/v1/runs/$RUN_ID/gates/H1" \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  -d "{
    \"action\": \"approve\",
    \"expected_run_version\": $RUN_VERSION,
    \"idempotency_key\": \"$(uuidgen)\",
    \"comment\": \"Reviewed by API client\"
  }"
```

H2 与 H4 使用同一结构，只替换 URL 中的 gate。真实 H2 run 如果存在多个可执行设计，应在请求中增加：

```json
{
  "selected_candidate_id": "candidate-id-from-design-arena"
}
```

### 3.3 H3 逐条主张决定

Fixture 证据不能支持实证主张，通常使用 `hold` 并生成计划：

```json
{
  "action": "generate_plan_only",
  "expected_run_version": 7,
  "idempotency_key": "a-new-uuid",
  "comment": "Fixture evidence is not empirical evidence.",
  "claims": [
    {
      "claim_id": "claim-id-from-run-state",
      "decision": "hold",
      "reason": "Fixture evidence cannot support an empirical claim."
    }
  ]
}
```

真实运行可以对每条 claim 使用：

- `approve`：证据与人工审查均允许原表述；
- `downgrade`：必须同时提供更保守的 `final_text`；
- `reject`；
- `hold`。

如果识别条件不满足，应使用 `generate_identification_failure_report`，不能把工程执行成功转写为因果结论。

### 3.4 可运行示例

仓库提供了完整客户端：

```bash
python examples/python_client.py --base-url "$HW_BASE_URL" --token "$HW_TOKEN"
```

它会创建 Fixture run，依次处理 H1–H4，并在完成时打印 `execution_status`、`scientific_status` 和 `plan_only`。

## 4. 上传 CSV 并创建真实研究 run

上传接口只接受一个 `.csv` 文件。文件内容作为原始 HTTP body 发送，文件名放在 query string：

```bash
curl -X POST \
  "$HW_BASE_URL/api/v1/case-imports/upload?filename=panel.csv" \
  -H "Content-Type: text/csv" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  --data-binary @panel.csv \
  -o import.json
```

响应包含：

```json
{
  "case_submission": {},
  "import_report": {
    "registered_dataset_id": "...",
    "row_count": 1000,
    "column_count": 12,
    "requires_human_confirmation": true,
    "human_review_items": []
  }
}
```

服务端保存真实路径，客户端只拿到不可变 `DatasetRef`。不要自行伪造 dataset id 或 SHA-256。

使用 `jq` 把导入结果送入 run：

```bash
jq '{
  mode: "research",
  model_provider: "code_owned",
  execution_mode: "external",
  case: .case_submission
}' import.json > create-run.json

curl -X POST "$HW_BASE_URL/api/v1/runs" \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  --data-binary @create-run.json
```

真实统计执行要求 Research Engine 已配置且可访问。`code_owned` 表示研究设计不调用外部 LLM；`qwen` 则要求 `DASHSCOPE_API_KEY`。

## 5. Group1 → Group2 接入

### 手动接入

该接口使用服务端本地路径，因此只适合可信的自托管环境：

```bash
curl -X POST "$HW_BASE_URL/api/v1/group1-handoffs/local/runs" \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  -d '{
    "path": "/evidence/I_group1_handoff",
    "mode": "research",
    "research_model_provider": "code_owned",
    "execution_panel_path": "/data/panel.csv",
    "execution_manifest_path": "/data/panel.manifest.json",
    "source_config_path": "/app/backend/config/group1_execution_sources.json"
  }'
```

三个执行绑定路径必须同时提供。缺任何一个时，系统保持 fail closed。

### 已验收执行包

```bash
curl "$HW_BASE_URL/api/v1/group1-handoffs/local/verified-bundle"
```

状态为 `ready` 后才可以：

```bash
curl -X POST \
  "$HW_BASE_URL/api/v1/group1-handoffs/local/verified-bundle/runs" \
  -H "X-Hypoweaver-Token: $HW_TOKEN"
```

公开仓库不附带 Group1 私有数据和验收回执，因此新克隆默认返回 `unavailable`。可通过以下服务端环境变量绑定自己的资产：

- `HYPOWEAVER_GROUP1_HANDOFF_PATH`
- `HYPOWEAVER_GROUP1_EXECUTION_PANEL_PATH`
- `HYPOWEAVER_GROUP1_EXECUTION_MANIFEST_PATH`
- `HYPOWEAVER_GROUP1_SOURCE_CONFIG_PATH`
- `HYPOWEAVER_GROUP1_ACCEPTANCE_RECEIPT_PATH`

## 6. 运行时模型配置

推荐在服务端环境变量中配置：

```text
DASHSCOPE_API_KEY
QWEN_MODEL
QWEN_BASE_URL
RESEARCH_ENGINE_URL
RESEARCH_ENGINE_TOKEN
```

也可以调用：

```bash
curl -X PUT "$HW_BASE_URL/api/v1/runtime-config" \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  -d '{
    "qwen_model": "qwen-plus",
    "qwen_api_key": "replace-at-runtime"
  }'
```

密钥不会在 GET 响应中回显。生产环境优先使用平台 secret/env，不要通过前端长期保存密钥。

连接测试：

```bash
curl -X POST "$HW_BASE_URL/api/v1/runtime-config/tests" \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HW_TOKEN" \
  -d '{"target":"research_engine"}'
```

## 7. Python 调用片段

```python
import httpx

base_url = "http://127.0.0.1:8000"
headers = {"X-Hypoweaver-Token": "replace-with-token"}

with httpx.Client(base_url=base_url, headers=headers, timeout=60) as client:
    run = client.post(
        "/api/v1/runs",
        json={"preset_case_id": "green-finance-did", "mode": "fixture"},
    ).raise_for_status().json()
    latest = client.get(f"/api/v1/runs/{run['id']}").raise_for_status().json()
    print(latest["status"], latest["current_gate"], latest["version"])
```

## 8. JavaScript/Agent 调用片段

```javascript
const baseUrl = 'http://127.0.0.1:8000'
const token = process.env.HYPOWEAVER_API_TOKEN

const response = await fetch(`${baseUrl}/api/v1/runs`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Hypoweaver-Token': token,
  },
  body: JSON.stringify({
    preset_case_id: 'green-finance-did',
    mode: 'fixture',
  }),
})

if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`)
console.log(await response.json())
```

推荐的外部 Agent 工具边界：

1. GET `/definitions/app-a` 与 `/openapi.json` 发现能力；
2. POST `/runs` 创建任务；
3. GET `/runs/{id}` 轮询状态；
4. 遇到 `waiting_human` 时停止自动推进，把 gate、version、候选设计/claims 展示给人；
5. 人工决定后调用 `/gates/{gate}`；
6. 读取 `/artifacts/{artifact_key}`，不要直接访问服务端文件路径。

## 9. 主要接口索引

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/definitions/app-a` | 工作流定义 |
| GET/PUT | `/api/v1/runtime-config` | 查看/更新运行时配置 |
| POST | `/api/v1/runtime-config/tests` | 测试模型或执行器连接 |
| POST | `/api/v1/case-imports/upload` | 上传主 CSV |
| POST | `/api/v1/case-imports/assets/upload` | 上传补充 CSV |
| GET/POST | `/api/v1/runs` | 列出/创建 run |
| GET/DELETE | `/api/v1/runs/{run_id}` | 获取/删除 run |
| POST | `/api/v1/runs/{run_id}/gates/{gate}` | H1–H4 人工决定 |
| POST | `/api/v1/runs/{run_id}/revisions` | 提交 H1/H2 修订 |
| POST | `/api/v1/runs/{run_id}/design/retry` | 重试设计阶段 |
| POST | `/api/v1/runs/{run_id}/writing/retry` | 重试写作阶段 |
| GET | `/api/v1/runs/{run_id}/artifacts/{key}` | 读取产物 envelope |
| GET | `/api/v1/runs/{run_id}/figures/{id}/{format}` | 下载图表文件 |
| GET/POST | `/api/v1/group1-handoffs/local/verified-bundle[/runs]` | 检查/启动已验收 Group1 包 |

## 10. 错误与重试

| HTTP | 含义 | 调用方动作 |
| ---: | --- | --- |
| 401 | token 缺失或错误 | 修正 `X-Hypoweaver-Token` |
| 403 | 远程写请求未配置服务端 token | 服务端设置 `HYPOWEAVER_API_TOKEN` |
| 404 | run、artifact 或 figure 不存在 | 停止并核对 id |
| 409 | 版本冲突、转换占用或存储上限 | 重新 GET 最新 run；不要盲重试旧决定 |
| 422 | 输入或工作流决定不符合契约 | 根据 `detail` 修正请求 |
| 503 | 模型/执行器未配置或不可用 | 检查 runtime config 与健康端点 |

所有写请求都应使用新的 `idempotency_key`。网络超时后可安全重发同一个 key；业务内容改变时必须换 key。`expected_run_version` 不匹配时重新读取 run，让人确认新的状态后再决定。
