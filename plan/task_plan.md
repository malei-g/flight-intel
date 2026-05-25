# Task Plan: flight-intel — 智能机票评分看板

## Goal
构建一个"上海 → 底特律，一个月后出发"智能机票评分看板系统，能自动抓取候选航班、多维度打分排序、并通过交互式 Dashboard 展示推荐结果。

## Phases

### Phase 0: 项目初始化
- [x] 创建项目目录 `/Users/ml/flight-intel`
- [x] 创建 plan 文件（task_plan.md / notes.md / implementation_plan.md）
- [ ] 初始化 `pyproject.toml` 和依赖配置
- [ ] 创建 `.env.example` 和 `.gitignore`
- [ ] 初始化 git 仓库

### Phase 1: 数据抓取层（Crawler/Fetcher）
- [ ] 安装 `google-flights-scraper` 并验证可用性
- [ ] 实现 `app/providers/google_flights_scraper.py`
- [ ] 实现 `app/services/flight_fetcher.py`（统一接口）
- [ ] 实现 `app/providers/mcp_client.py`（MCP 备用数据源占位）
- [ ] 编写抓取结果的 Schema（`app/schemas.py`）
- [ ] 用真实路线测试抓取（上海→底特律，+30天）

### Phase 2: 评分引擎（Scoring Engine）
- [ ] 实现 `app/services/scorer.py`（规则打分）
- [ ] 实现 `app/services/recommender.py`（Top N + 推荐理由）
- [ ] 编写 `tests/test_scorer.py`（边界条件覆盖）
- [ ] 验证打分权重：价格40% / 时长25% / 中转次数20% / 中转风险10% / 时刻5%

### Phase 3: API 层（FastAPI）
- [ ] 实现 `app/main.py`（FastAPI 入口）
- [ ] 实现 `app/api/routes_search.py`（`/search` 路由）
- [ ] 实现 `app/api/routes_score.py`（`/score` 路由）
- [ ] 实现 `app/config.py`（环境配置管理）
- [ ] 编写 `tests/test_api.py`
- [ ] 本地启动 uvicorn 验证接口

### Phase 4: Dashboard 层（Streamlit）
- [ ] 实现 `dashboard/streamlit_app.py`（MVP 看板）
- [ ] 功能：结果表 + 分数排序 + 价格分布图 + 时长分布图 + 推荐理由
- [ ] 本地启动 Streamlit 验证展示效果

### Phase 5: 数据管道与脚本
- [ ] 实现 `scripts/run_fetch.py`（一键抓取并存储）
- [ ] 实现 `scripts/run_score.py`（批量打分）
- [ ] 实现 `scripts/seed_demo_data.py`（生成 Demo 数据，无需真实抓取即可开发）

### Phase 6: 完善与交付
- [ ] 补充 `README.md`（安装、运行、配置说明）
- [ ] 补充 `docker-compose.yml`（可选容器化）
- [ ] 最终集成测试

## Key Questions
1. `google-flights-scraper` 当前是否需要 Playwright 浏览器驱动？是否有频率限制？
2. 评分权重是否应允许用户在 Dashboard 动态调整？
3. 历史价格数据如何持久化（SQLite / Parquet / CSV）？
4. MCP 层是作为 Fallback 还是默认数据源？

## Decisions Made
- **技术栈**: Python 3.11+, uv 包管理, FastAPI, Streamlit, Plotly, Pydantic v2
- **数据源优先级**: google-flights-scraper (Primary) → mcp-flight-search (Fallback)
- **打分模型**: 规则模型 MVP，后期可插拔替换为 ML 模型
- **持久化**: Phase 1 先用 CSV/JSON，后期升级 SQLite
- **Dashboard**: MVP 用 Streamlit，增强版可迁移 Dash

## Errors Encountered
（无）

## Status
**Sprint 4 完成** — app/main.py、routes_search.py、routes_score.py、config.py 全部完成，uvicorn 正常启动，/health /search /score 接口验证通过，test_api.py 19 个用例 + test_scorer.py 23 个用例 = **42/42 全过**。
**项目状态**: MVP 全部 Sprint（1/2/3/4）完成，可运行。
