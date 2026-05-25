# Flight Intel ✈

智能机票评分看板 — 自动抓取候选航班、多维度评分排序、交互式推荐展示。

默认路线：**上海 PVG → 底特律 DTW，出发日期 +30 天**（可自定义）。

---

## 功能

| 模块 | 说明 |
|------|------|
| 数据抓取 | `fast-flights`（Google Flights SSR，无需 API Key） |
| 评分引擎 | 5 维度规则模型：价格 40% / 时长 25% / 中转次数 20% / 中转风险 10% / 时刻 5% |
| FastAPI | `GET /search`、`POST /score`，权重可通过参数实时调整 |
| Streamlit 看板 | KPI 行 + Top N 推荐卡片 + 分项评分条 + 价格/时长分布图 |
| 数据源切换 | `demo`（本地 mock）/ `google`（实时查询），侧边栏一键切换 |

> **关于航班号**：看板中显示的航班号（如 `AC-001`）为系统按航司 IATA 代码自动生成的**虚拟标识**，格式为 `{承运人IATA}-{序号}`。这是因为 `fast-flights` 通过 Google Flights SSR 抓取数据，底层 API 不提供真实航班号字段。虚拟号仅用于排序、去重与会话内追踪，不可用于预订或查询航班状态。

---

## 快速启动

### 本地开发（推荐）

**前提**：已安装 [uv](https://docs.astral.sh/uv/)

```bash
git clone <repo>
cd flight-intel

# 安装依赖
uv sync --extra dev

# 复制环境配置
cp .env.example .env

# 1. 启动 API（端口 18765）
PYTHONPATH=. uv run uvicorn app.main:app --port 18765 --reload

# 2. 启动看板（端口 18766，新终端）
PYTHONPATH=. uv run streamlit run dashboard/streamlit_app.py --server.port 18766

# 3. 运行测试
uv run pytest
```

打开 <http://localhost:18766> 查看看板，<http://localhost:18765/docs> 查看 API 文档。

### Docker 一键启动

```bash
cp .env.example .env          # 按需修改 FLIGHT_PROVIDER
docker compose up --build
```

| 服务 | 地址 |
|------|------|
| Streamlit 看板 | <http://localhost:18766> |
| FastAPI + Swagger | <http://localhost:18765/docs> |

---

## 项目结构

```
flight-intel/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 环境配置
│   ├── schemas.py               # Pydantic 数据模型
│   ├── api/
│   │   ├── routes_search.py     # GET /search
│   │   └── routes_score.py      # POST /score
│   ├── services/
│   │   ├── scorer.py            # 规则打分引擎
│   │   ├── recommender.py       # Top N + 推荐理由
│   │   └── flight_fetcher.py    # 统一抓取接口
│   └── providers/
│       └── fast_flights_provider.py  # Google Flights 适配器
├── dashboard/
│   └── streamlit_app.py         # 交互式看板
├── scripts/
│   ├── seed_demo_data.py        # 生成 mock 数据
│   └── run_fetch.py             # CLI 抓取 + 打分
├── tests/
│   ├── test_scorer.py           # 打分引擎单元测试（23 用例）
│   └── test_api.py              # API 集成测试（19 用例）
├── data/
│   ├── raw/                     # 原始抓取结果
│   └── processed/               # 打分后结果
├── plan/                        # 项目规划文档
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.dashboard
└── pyproject.toml
```

---

## API 接口

### `GET /search` — 搜索并评分

```bash
curl "http://localhost:18765/search?origin=PVG&destination=DTW&provider=demo&top_n=5"
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `origin` | `PVG` | 出发机场 IATA 代码 |
| `destination` | `DTW` | 目的地机场 IATA 代码 |
| `depart_date` | 今天+30天 | `YYYY-MM-DD` |
| `provider` | 环境变量 | `demo` \| `google` |
| `top_n` | `10` | 返回条数（1–100） |
| `w_price` … `w_time_comfort` | 见下 | 各维度权重，合计须 ≈ 1.0 |

### `POST /score` — 对自定义航班列表打分

```bash
curl -X POST "http://localhost:18765/score" \
  -H "Content-Type: application/json" \
  -d '{"flights": [...]}'
```

### `GET /health`

```bash
curl http://localhost:18765/health
# {"status":"ok"}
```

---

## 打分权重

| 维度 | 默认权重 | 环境变量 |
|------|---------|---------|
| 价格 | 40% | `WEIGHT_PRICE` |
| 总飞行时长 | 25% | `WEIGHT_DURATION` |
| 中转次数 | 20% | `WEIGHT_STOPS` |
| 中转风险 | 10% | `WEIGHT_TRANSFER_RISK` |
| 起降时刻舒适度 | 5% | `WEIGHT_TIME_COMFORT` |

权重可通过 API 查询参数或 Streamlit 侧边栏实时调整，无需重启。

---

## 常用脚本

```bash
# 生成 20 条 mock 数据（可复现，seed=42）
PYTHONPATH=. uv run python scripts/seed_demo_data.py

# 真实抓取 PVG→DTW，输出 Top 10，结果写入 data/processed/
PYTHONPATH=. uv run python scripts/run_fetch.py --provider google --top 10
```

---

## 环境变量

复制 `.env.example` 为 `.env` 后修改：

```bash
FLIGHT_PROVIDER=demo      # demo | google
API_HOST=127.0.0.1
API_PORT=18765
WEIGHT_PRICE=0.40
WEIGHT_DURATION=0.25
WEIGHT_STOPS=0.20
WEIGHT_TRANSFER_RISK=0.10
WEIGHT_TIME_COMFORT=0.05
```

---

## 测试

```bash
uv run pytest              # 42 个用例全部通过
uv run pytest -v --tb=short
```

---

## 技术栈

- **Python 3.11+** · **uv** 包管理
- **FastAPI** + **uvicorn** — API 层
- **Streamlit** + **Plotly** — 看板
- **Pydantic v2** — 数据验证
- **fast-flights** — Google Flights SSR 抓取（无需 API Key）
- **pytest** — 测试
