# Future9 模拟评估 Demo

这是一个本地演示：20 名匿名模拟学生、9 项素养和 36 项技能。所有页面固定标明“模拟测试数据 / AI 自动评估 / 非正式成绩”；角色切换仅切换视图，不是认证，也不产生排名。

## 安装与启动

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Node.js（含 pnpm）。

```sh
uv sync
cd frontend && pnpm install
```

后端首次启动会自动在 `backend/app/data/app.db` 写入可重复的模拟学校、班级、学生、量规和已完成的演示结果：

```sh
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

另一个终端启动前端（`/api` 会代理到 8000）：

```sh
cd frontend && pnpm dev
```

需要单独消费排队任务时运行：

```sh
uv run python -m backend.app.worker
```

## 模式与环境变量

默认 `DEMO_AGENT_MODE=true`：worker 不调用外部模型，而是按证据长度做确定性演示评估。图像证据默认关闭；设置 `VISION_ENABLED=true` 后才接受图片。

要使用真实 DeepAgents，设置 `DEMO_AGENT_MODE=false`，并按所选 LangChain/OpenAI 兼容模型配置对应环境变量（通常为 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`）。这会调用外部模型，成本、可用性和结果均不属于默认 demo 承诺。

## API

- `GET /api/demo/context`、`GET /api/rubrics/current`
- `GET /api/dashboard/school`、`GET /api/classes/{id}/dashboard`、`GET /api/students/{id}/profile`
- `POST /api/evidence`（JSON 或 multipart）、`POST /api/assessment-jobs`
- `GET /api/assessment-jobs/{id}`、`GET /api/assessment-jobs/{id}/events`（SSE）
- `PATCH /api/assessments/{result_id}`（保留原结果，追加人工修订）

## 验证

```sh
uv run pytest -q
cd frontend
pnpm test
pnpm typecheck
pnpm build
pnpm test:e2e
```

E2E 通过浏览器提交“模拟测试数据”证据、创建任务，在一个子进程中运行 worker，再检查 SSE/轮询完成及学生、学校视图刷新。首次运行如缺 Chromium，执行 `pnpm exec playwright install chromium`。
