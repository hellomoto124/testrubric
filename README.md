# 凯风雨旸小学素养评估 Demo

本地 V0.2 Demo：1 所模拟学校、3 个班、20 名匿名模拟学生，使用学校版 3 个育人目标、10 项素养能力、38 项技能和 228 个 Level 单元。所有页面固定标明“模拟测试数据 / AI 自动评估 / 非正式成绩”；角色切换不是认证，不产生总分或排名。

连续评分由后端 `anchor_interp_v1` 确定性计算：完整 Level、相邻 Level 进度、0–600 水平分、未知区间和目标差距。AI 只提交指标 0–4 档、未知、无关或冲突，不提交权重和最终分数。三年级默认目标 Level 3、Level 2 基础、Level 4 优秀是凯风雨旸小学本土演示规则，不是 Future9 官方年级规则。

## 环境与安装

需要 Python 3.12、uv、Node.js、pnpm 和团队提供的 `rtk`。

```sh
rtk uv sync
rtk pnpm --dir frontend install
```

后端首次启动会初始化 SQLite。演示种子可重复运行，不触碰非模拟学生或真实/人工结果。

```sh
rtk uv run --env-file .env uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
rtk uv run --env-file .env python -m backend.app.worker
rtk pnpm --dir frontend dev --host 127.0.0.1 --port 5173
```

## 学校量规导入

仓库运行时读取标准化文件 `backend/app/data/kai_feng_yuyang_260910.json`，不依赖 Downloads 路径。重新生成时使用未提交的原始 Excel：

```sh
rtk uv run python tools/import_yuyang_rubric.py \
  /Users/xiexiaodong/Downloads/雨旸素养框架.xlsx \
  --sheet 素养量规表-260910 \
  --output backend/app/data/kai_feng_yuyang_260910.json
```

导入器保留中英文名、子技能、出处、Excel 行号、六级描述及项目符号指标。Legacy 9/36 量规和结果仍可通过原 `/api` 路由读取，旧结果标记 `legacy_unscored`，不会自动补成 `Level × 100`。

## 千问 / OpenAI-compatible 配置

默认 `DEMO_AGENT_MODE=true`，worker 使用确定性模拟判断但仍经过同一个后端评分函数。真实 Deep Agents 仅从 Git 忽略的 `.env` 读取配置：

```dotenv
DEMO_AGENT_MODE=false
OPENAI_COMPATIBLE_MODEL=qwen3.5-plus
OPENAI_COMPATIBLE_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-local-secret
VISION_ENABLED=false
```

不要提交或记录真实密钥。只有模型明确支持视觉且 `VISION_ENABLED=true` 时才接受 JPG/PNG。

## V2 API

- `GET /api/v2/rubrics/current`
- `GET /api/v2/skills/{code}/scoring-rubric`
- `POST /api/v2/scoring-rubrics/drafts`
- `PATCH /api/v2/scoring-rubrics/{id}`
- `POST /api/v2/scoring-rubrics/{id}/publish`
- `GET /api/v2/targets`
- `PUT /api/v2/targets/{grade}/{term}/{skill_code}`
- `POST /api/v2/assessment-jobs`
- `GET /api/v2/assessment-jobs/{id}`
- `GET /api/v2/assessment-jobs/{id}/events`
- `POST /api/v2/assessments/{result_id}/revisions`
- `GET /api/v2/students/{id}/skills/{code}/history`
- `GET /api/v2/dashboard/{school|class|student}/{id}`
- `GET /api/v2/scoring-rubrics?skill_code={code}`
- `GET /api/v2/reports/audit`
- `GET /api/v2/system/status`
- `PUT /api/v2/system/settings`

任务锁定量规、评分配置、目标、学生和证据快照。worker 按 `evidence_extractor → rubric_assessor → host scoring → feedback_writer` 顺序执行，最多重试两次。修订追加保存并由后端重算；不同量规或评分版本不连成同一趋势。

## Figma 与前端

Figma 设计文件：[凯风雨旸小学素养评估系统｜学校总览与个人画像](https://www.figma.com/design/O6v7M50dNj5vVYM5lkHOR6)

设计含学校总览和个人画像的 1440/390 页面，以及 834 平板规则。React 使用现有 CSS 与 ECharts，不引入 Tailwind、Motion、UI 组件库或状态库。图表有文字替代；区间不取中点，未观察不画为 0；支持 `prefers-reduced-motion`。

侧栏首期管理页面包括：素养体系（目标与评分配置版本）、报告中心（学校/班级/个人/审计网页报告）和系统设置（学期、模型脱敏状态、worker、数据库与量规健康状态）。系统设置不显示或修改API Key，也不提供删除、重置、正式权限或多学校配置。

## 验证

### 素养成长看板

侧栏“素养成长看板”参考成绩看板的筛选、素养点亮矩阵、证据下钻、画像对比和导师摘要交互，使用凯风雨旸学校量规：

- 关怀者：通情达理、公共参与、多元共生。
- 创造者：明己励志、参与探究、解决问题、表达想法。
- 学习者：学会学习、读懂世界、定量推理。

支持班级、匿名学生、观察阶段、育人目标与素养状态筛选，勾选最多两名学生并排查看；点击矩阵单元查看技能、六级量规、原始模拟证据和同版本同情境成长记录。个人成长档案同样显示10维画像及三个育人目标。

整体学生雷达图展示全校或所选班级的10项素养，沿用三个育人目标的分色。后端 `cohort` 先取每名学生已评点分技能的较低中位 Level，再取学生间的较低中位 Level；附有效人数与技能覆盖率（覆盖包含点分和区间）。只受班级与观察阶段影响，不受姓名、目标或状态筛选影响。缺少维度时不补零连成多边形，已知值仍在明细表展示；图形面积不表示总分或排名。当前数据仍为模拟测试数据。

能力 Level 取已形成点分技能的较低中位数，同时报告覆盖率。全部技能都有明确点分且达到任务锁定目标，才点亮整项能力；缺证不记零，区间不取中点，冲突要求复核，不使用最高历史分代替最新表现。

初始化会额外创建 `seed_kanban_v1` 的1,160条模拟结果与对应证据：20名学生×38技能的最新阶段，以及每项能力代表技能的两次早期观察（9月1日、8日、15日）。所有结果调用同一个 `anchor_interp_v1` 生成，标记模拟、未校准；仅写模拟学生，重复初始化不重复添加，真实评估与人工修订优先于种子。原228条 V2 种子及 Legacy 记录保留。

新增只读 API：

- `GET /api/v2/competency-board?class_id=1&name=01&stage=latest`
- `GET /api/v2/students/{id}/competency-profile?stage=latest`
- `GET /api/v2/students/{id}/capabilities/{code}?stage=latest`

`stage` 支持 `latest`、`baseline`、`midpoint`。看板是发展性评价视图，未接入外站学生数据或考试成绩规则。

```sh
rtk uv run pytest -q
rtk uv run ruff check backend tools
rtk pnpm --dir frontend test
rtk pnpm --dir frontend typecheck
rtk pnpm --dir frontend build
rtk pnpm --dir frontend test:e2e
rtk git diff --check
```

E2E 使用隔离 SQLite，完成“上传 TXT/文字证据 → 创建 V2 任务 → worker → SSE 完成 → 个人刷新 → 学校刷新”，并验证 375、768、1440 宽度无页面级横向溢出。
