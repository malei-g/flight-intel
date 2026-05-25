# Notes: flight-intel 技术调研

## 来源文档
- `/Users/ml/机票评分看板规划设计.md`

---

## 依赖库调研

### google-flights-scraper
- PyPI: https://pypi.org/project/google-flights-scraper/
- 用途: 抓取 Google Flights 数据，含价格、时长、中转数、日期
- 底层: Playwright（需要 `playwright install`）
- 使用方式: Python API 直接调用

### flights-mcp-server
- GitHub: https://github.com/smamidipaka6/flights-mcp-server
- 用途: Google Flights MCP Server，供 LLM/自动化脚本使用
- 定位: 工具层 / 自动化接口

### mcp-flight-search
- PyPI: https://pypi.org/project/mcp-flight-search/
- 用途: 结构化程度高的 MCP flight search 参考实现
- 定位: 参考项目结构，作为 MCP 备用数据源

### Flight-Price-Prediction-Streamlit
- 技术: FastAPI + Streamlit
- 用途: 输入航线后预测票价/推荐，适合做原型参考

### Monitor-Webscraped-Flight-Prices-using-Dash-and-Plotly
- GitHub: https://github.com/JosephZahar/Monitor-Webscraped-Flight-Prices-using-Dash-and-Plotly
- 技术: Dash + Plotly
- 用途: 票价趋势、候选航班列表、筛选器

---

## 打分规则权重

| 维度 | 权重 | 说明 |
|------|------|------|
| 价格 | 40% | 越低越好，相对最低价归一化 |
| 总飞行时长 | 25% | 越短越好，含中转等待 |
| 中转次数 | 20% | 直飞 > 一次中转 > 多次中转 |
| 中转风险 | 10% | 中转时间、机场规模、赶机风险 |
| 时刻舒适度 | 5% | 避免红眼/凌晨航班 |

**进阶调整建议**: 若更在意出行体验而非最低价，可将"时长+中转质量"提至 50%，价格降至 30%。

---

## MVP 实施顺序（来自规划文档）

1. 建仓库和基础目录
2. 接 `google-flights-scraper`，拿到原始航班数据
3. 写 `scorer.py`，做规则打分
4. 写 Streamlit 看板，先展示结果表和排序
5. 再补 FastAPI 和测试
6. 最后考虑接 MCP 或预测模型

---

## 文件结构（规划文档原版）

```
flight-intel/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes_search.py
│   │   └── routes_score.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── flight_fetcher.py
│   │   ├── scorer.py
│   │   └── recommender.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── google_flights_scraper.py
│   │   └── mcp_client.py
│   └── utils/
│       ├── __init__.py
│       ├── date_utils.py
│       └── logging.py
├── dashboard/
│   ├── streamlit_app.py
│   └── assets/
├── tests/
│   ├── test_scorer.py
│   └── test_api.py
├── data/
│   ├── raw/
│   └── processed/
└── scripts/
    ├── run_fetch.py
    ├── run_score.py
    └── seed_demo_data.py
```

---

## 开发环境命令

```bash
# 使用 uv 管理（符合 Claude Scholar 偏好）
uv init flight-intel
uv add fastapi uvicorn streamlit pandas pydantic plotly playwright
uv add --dev pytest mypy ruff

# Playwright 浏览器驱动
playwright install chromium
```
