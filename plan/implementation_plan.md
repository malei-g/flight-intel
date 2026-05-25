# flight-intel 项目实施方案

> 智能机票评分看板 — 上海 → 底特律，一个月后出发
> 生成日期：2026-05-25

---

## 一、项目目标

输入出发地、目的地、出发日期，自动抓取候选航班并进行多维度评分，以交互式看板展示 Top N 推荐，辅助购票决策。

**最小可用版本（MVP）实现 5 件事：**
1. 抓取候选票
2. 计算评分
3. 排序展示
4. 保存历史结果
5. 推荐理由输出

---

## 二、技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 包管理 | `uv` | 符合项目默认配置标准 |
| 配置管理 | Hydra + OmegaConf | 实验可复现，符合 Claude Scholar 默认 |
| 数据抓取 | `google-flights-scraper` (Playwright) | 最贴近需求，Python 原生 |
| 备用数据源 | `mcp-flight-search` | 结构化接口，低维护成本 |
| 数据验证 | Pydantic v2 | 类型安全，与 FastAPI 深度集成 |
| API 层 | FastAPI + uvicorn | 轻量、类型友好、异步支持 |
| 看板 MVP | Streamlit | 快速迭代，交互内置 |
| 看板增强版 | Dash + Plotly | 复杂交互与可定制布局 |
| 持久化 | CSV → SQLite（后期升级） | MVP 阶段简单可用 |
| 测试 | pytest | 标准 Python 测试框架 |
| 代码质量 | ruff + mypy | 符合代码风格规范 |

---

## 三、文件结构

```
flight-intel/
├── plan/                        # 项目计划（本目录）
│   ├── task_plan.md
│   ├── notes.md
│   └── implementation_plan.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml
│
├── app/                         # 后端核心
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 环境/Hydra 配置
│   ├── schemas.py               # Pydantic 数据模型
│   │
│   ├── api/                     # 路由层
│   │   ├── __init__.py
│   │   ├── routes_search.py     # GET /search
│   │   └── routes_score.py      # POST /score
│   │
│   ├── services/                # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── flight_fetcher.py    # 统一抓取接口
│   │   ├── scorer.py            # 规则打分引擎
│   │   └── recommender.py       # Top N + 推荐理由
│   │
│   ├── providers/               # 数据源适配层
│   │   ├── __init__.py
│   │   ├── google_flights_scraper.py
│   │   └── mcp_client.py        # MCP 备用（占位）
│   │
│   └── utils/
│       ├── __init__.py
│       ├── date_utils.py
│       └── logging.py
│
├── dashboard/
│   ├── streamlit_app.py         # MVP 看板
│   └── assets/
│
├── tests/
│   ├── test_scorer.py
│   └── test_api.py
│
├── data/
│   ├── raw/                     # 原始抓取结果（JSON/CSV）
│   └── processed/               # 打分后的结果
│
└── scripts/
    ├── run_fetch.py             # 一键抓取
    ├── run_score.py             # 批量打分
    └── seed_demo_data.py        # Demo 数据生成
```

---

## 四、核心数据模型（schemas.py 草稿）

```python
from pydantic import BaseModel
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class SearchConfig:
    origin: str          # e.g. "PVG"
    destination: str     # e.g. "DTW"
    depart_date: str     # e.g. "2026-06-25"
    passengers: int = 1

class FlightSegment(BaseModel):
    airline: str
    flight_no: str
    depart_time: datetime
    arrive_time: datetime
    duration_min: int
    layover_min: Optional[int] = None
    layover_airport: Optional[str] = None

class FlightOption(BaseModel):
    id: str
    price_usd: float
    total_duration_min: int
    stops: int                    # 0=直飞
    segments: list[FlightSegment]
    is_red_eye: bool = False
    raw_data: dict = {}

class ScoredFlight(BaseModel):
    flight: FlightOption
    score: float                  # 0–100
    rank: int
    recommend_reason: str
    buy_or_wait: str              # "BUY" | "WAIT" | "SKIP"
    score_breakdown: dict         # 各维度分项得分
```

---

## 五、打分规则（scorer.py 核心逻辑）

### 权重配置

```python
SCORE_WEIGHTS = {
    "price":          0.40,   # 价格
    "duration":       0.25,   # 总飞行时长
    "stops":          0.20,   # 中转次数
    "transfer_risk":  0.10,   # 中转风险
    "time_comfort":   0.05,   # 起降时刻舒适度
}
```

### 各维度归一化规则

| 维度 | 归一化方式 |
|------|-----------|
| 价格 | `(max_price - price) / (max_price - min_price)` |
| 时长 | `(max_dur - duration) / (max_dur - min_dur)` |
| 中转次数 | 直飞=1.0，1次=0.6，2次=0.2，3次+=0.0 |
| 中转风险 | 中转时长<45min=0.0, 45-90=0.5, >90=1.0；低风险机场加成 |
| 时刻舒适 | 6-22时出发=1.0，23-1时=0.5，2-5时=0.0 |

### 输出结构

```python
{
  "score": 82.5,
  "rank": 1,
  "recommend_reason": "价格低于均值 18%，直飞 14h，起飞时间适宜",
  "buy_or_wait": "BUY",
  "score_breakdown": {
    "price_score": 88,
    "duration_score": 75,
    "stops_score": 100,
    "transfer_risk_score": 100,
    "time_comfort_score": 80
  }
}
```

---

## 六、API 接口设计

### `GET /search`
```
参数: origin, destination, depart_date, passengers
返回: List[ScoredFlight]（已按 score 降序）
```

### `POST /score`
```
Body: List[FlightOption]（外部传入原始航班数据）
返回: List[ScoredFlight]
```

---

## 七、Dashboard 页面规划（Streamlit MVP）

| 区域 | 内容 |
|------|------|
| 顶部表单 | 出发地 / 目的地 / 日期 / 人数 |
| 推荐卡片 | Top 3 航班，显示评分、价格、时长、推荐理由、BUY/WAIT 标签 |
| 结果表格 | 全部候选航班，支持按评分/价格/时长排序 |
| 价格分布图 | Plotly 直方图 |
| 时长分布图 | Plotly 散点图（时长 vs 价格） |
| 历史记录 | 本次抓取时间 + 数据来源 |

---

## 八、实施顺序（Sprint 划分）

### Sprint 1（Day 1–2）：脚手架 + Demo 数据
- [ ] `uv init` + 依赖安装
- [ ] `scripts/seed_demo_data.py` 生成 20 条 mock 航班
- [ ] `app/schemas.py` 完成数据模型
- [ ] `app/services/scorer.py` 完成打分逻辑
- [ ] `tests/test_scorer.py` 通过

### Sprint 2（Day 3–4）：真实数据抓取
- [ ] `google-flights-scraper` 集成与验证
- [ ] `app/providers/google_flights_scraper.py`
- [ ] `app/services/flight_fetcher.py`
- [ ] `scripts/run_fetch.py` 端到端测试

### Sprint 3（Day 5）：看板 MVP
- [ ] `dashboard/streamlit_app.py`（基于 Demo 数据先跑通）
- [ ] 接入真实打分结果
- [ ] 完成推荐卡片 + 分布图

### Sprint 4（Day 6–7）：API + 测试
- [ ] FastAPI 路由实现
- [ ] `tests/test_api.py`
- [ ] `README.md` + docker-compose

---

## 九、快速启动命令

```bash
# 1. 初始化项目
cd /Users/ml/flight-intel
uv init .
uv add fastapi uvicorn streamlit pandas pydantic plotly playwright
uv add --dev pytest mypy ruff
playwright install chromium

# 2. 生成 Demo 数据（无需真实抓取）
uv run python scripts/seed_demo_data.py

# 3. 启动 Streamlit 看板
uv run streamlit run dashboard/streamlit_app.py

# 4. 启动 API 服务
uv run uvicorn app.main:app --reload

# 5. 运行测试
uv run pytest
```

---

## 十、后期扩展方向

| 方向 | 说明 |
|------|------|
| ML 价格预测 | 接入 `flight_price_prediction`，将规则模型升级为学习型 |
| MCP 集成 | 接入 `flights-mcp-server`，支持 LLM Agent 自动查询 |
| 价格监控 | 定时抓取 + 历史趋势图 + 价格下跌提醒 |
| 多路线支持 | 不限于上海→底特律，支持任意路线 |
| Dash 增强版 | 替换 Streamlit 为 Dash，支持更复杂交互 |
| 容器化部署 | 完善 docker-compose，支持一键启动全栈 |
