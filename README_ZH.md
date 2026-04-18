# BarFlow

**轻量级、免费的美股市场数据管道 — 基于 [Polygon.io](https://polygon.io)。**  
一键抓取、存储并每日更新全美普通股的日线行情、分红及拆股数据。

> English version: [README.md](README.md)

---

## 功能概览

- 下载约 10,000 只美股普通股（含在市及已退市）的每日 OHLCV 行情
- 追踪分红与拆股历史，并提供预计算的后复权因子
- 所有数据以 Parquet 格式存储，支持 pandas 快速读取
- 断点续传 — 中断后直接重跑，已缓存日期自动跳过
- 专为 **Polygon.io 免费版**设计（每分钟 5 次调用），无需付费

---

## 项目结构

```
BarFlow/
├── config.py               # 所有参数（API Key、日期、路径等）
├── main.py                 # 全量管道 — 首次运行以初始化数据
├── daily_update.py         # 增量更新 — 每个交易日收盘后运行
├── fetch_stock_basic.py    # 从 Polygon.io 抓取股票基础信息
├── fetch_daily.py          # 从 Polygon.io 抓取 OHLCV 日线（含断点续传）
├── fetch_dividends.py      # 抓取分红历史
├── fetch_splits.py         # 抓取拆股历史
├── utils.py                # 限速器、HTTP 工具、分页器
├── raw_daily_cache/        # 每日缓存文件（自动生成）
└── output/                 # 最终 Parquet 输出文件（自动生成）
```

---

## 快速开始

**1. 安装依赖**
```bash
pip install -r requirements.txt
```

**2. 获取免费 API Key**，前往 [polygon.io](https://polygon.io) 注册，无需信用卡。

**3. 打开 `config.py`，填入你的 Key：**
```python
POLYGON_API_KEY = "your_polygon_key_here"
```

**4. 运行全量初始化**（免费版约 70 分钟）：
```bash
python main.py
```

**5. 每日增量更新** — 每个交易日收盘后运行：
```bash
python daily_update.py
```

中途中断后直接重跑，已缓存日期自动跳过。

**其他模式：**
```bash
python main.py --daily-only       # 仅更新日线
python main.py --corporate-only   # 仅更新分红和拆股
```

---

## 读取数据

```python
import pandas as pd

daily    = pd.read_parquet("output/US_Share_Daily.parquet")
basic    = pd.read_parquet("output/US_Share_Stock_Basic_All.parquet")
dividend = pd.read_parquet("output/US_Share_Dividend.parquet")
splits   = pd.read_parquet("output/US_Share_Splits.parquet")
```

**常用查询：**
```python
# 仅在市股票
active = basic[basic["active"] == True]["ticker"].tolist()

# 纳斯达克股票
nasdaq = basic[basic["primary_exchange"] == "XNAS"]["ticker"].tolist()

# 按日期范围筛选
mask = (daily["date"] >= pd.to_datetime("2025-06-01").date()) & \
       (daily["date"] <= pd.to_datetime("2025-12-31").date())
h2_2025 = daily[mask]
```

---

## 复权价格

所有价格为原始未复权价格。使用复权因子计算后复权价格：

```
adj_price = raw_price × split_factor × div_factor
```

```python
def get_adj_close(ticker: str) -> pd.DataFrame:
    df = daily[daily["ticker"] == ticker][["date", "close"]].copy().sort_values("date")

    t_splits = (
        splits[splits["ticker"] == ticker]
        [["execution_date", "historical_adjustment_factor"]]
        .rename(columns={"execution_date": "date", "historical_adjustment_factor": "split_factor"})
        .sort_values("date")
    )
    t_divs = (
        dividend[dividend["ticker"] == ticker]
        [["ex_dividend_date", "historical_adjustment_factor"]]
        .rename(columns={"ex_dividend_date": "date", "historical_adjustment_factor": "div_factor"})
        .sort_values("date")
    )

    df = pd.merge_asof(df, t_splits, on="date", direction="forward").fillna({"split_factor": 1.0})
    df = pd.merge_asof(df, t_divs,   on="date", direction="forward").fillna({"div_factor":   1.0})
    df["adj_close"] = df["close"] * df["split_factor"] * df["div_factor"]
    return df[["date", "close", "adj_close"]]

aapl = get_adj_close("AAPL")
```

若日期 D 之后无对应事件，因子默认为 1.0。

---

## 数据字典

### US_Share_Stock_Basic_All.parquet
所有美股普通股的基础信息（含在市及已退市）。更新方式：全量覆盖。

| 列名 | 类型 | 说明 |
|------|------|------|
| `ticker` | string | 股票代码 |
| `name` | string | 公司全称 |
| `active` | boolean | `True` 表示当前在市 |
| `primary_exchange` | string | 交易所代码（如 `XNAS`、`XNYS`） |
| `list_date` | date | 上市日期 |
| `delisted_utc` | date | 退市日期（在市则为空） |
| `market_cap` | float | 市值（美元） |
| `sic_code` / `sic_description` | string | SIC 行业分类 |
| `cik` | string | SEC 注册号 |
| `composite_figi` | string | 彭博 FIGI 标识符 |
| `weighted_shares_outstanding` | float | 加权流通股数 |
| `total_employees` | Int64 | 员工总数 |
| `homepage_url` | string | 公司官网 |

### US_Share_Daily.parquet
2025-01-01 起的原始日线 OHLCV 数据。更新方式：追加。

| 列名 | 类型 | 说明 |
|------|------|------|
| `date` | date | 交易日期 |
| `ticker` | string | 股票代码 |
| `open` / `high` / `low` / `close` | float | 原始未复权价格（美元） |
| `volume` | float | 成交量（股数） |
| `vwap` | float | 成交量加权均价 |
| `transactions` | Int64 | 成交笔数 |

### US_Share_Dividend.parquet
2025-01-01 起的分红事件。更新方式：全量覆盖。

| 列名 | 类型 | 说明 |
|------|------|------|
| `ticker` | string | 股票代码 |
| `ex_dividend_date` | date | 除息日 |
| `pay_date` | date | 派息日 |
| `cash_amount` | float | 每股分红金额（美元） |
| `split_adjusted_cash_amount` | float | 经后续拆股调整后的每股分红 |
| `distribution_type` | string | `recurring` / `special` / `supplemental` / `irregular` |
| `frequency` | Int64 | 年度频率：1=年度，2=半年，4=季度，12=月度 |
| `historical_adjustment_factor` | float | 仅含分红的累积后复权因子 |

### US_Share_Splits.parquet
2025-01-01 起的拆股事件。更新方式：全量覆盖。

| 列名 | 类型 | 说明 |
|------|------|------|
| `ticker` | string | 股票代码 |
| `execution_date` | date | 拆股执行日期 |
| `adjustment_type` | string | `forward_split` / `reverse_split` / `stock_dividend` |
| `split_from` / `split_to` | float | 拆股比例（如 1→4 表示四拆一） |
| `historical_adjustment_factor` | float | 仅含拆股的累积后复权因子 |

---

## 配置参数

所有参数均在 `config.py` 中：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `POLYGON_API_KEY` | — | Polygon.io API Key |
| `START_DATE` | `2025-01-01` | 数据起始日期 |
| `END_DATE` | 昨日 | 数据截止日期 |
| `TICKER_TYPE` | `CS` | 股票类型过滤 |
| `RATE_LIMIT_CALLS` | `5` | 每窗口最大调用次数 |
| `RATE_LIMIT_PERIOD` | `60` | 限速窗口（秒） |
| `FORCE_REFRESH_STOCK_BASIC` | `False` | 强制重新抓取股票基础信息 |

---

## 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 当日数据 `403` | 免费版无法访问当日数据 | 已修复，`END_DATE` 默认为昨日 |
| 任意日期 `403` | API Key 错误或未填写 | 检查 `config.py` 中的 `POLYGON_API_KEY` |
| 分红/拆股 `404` | Base URL 配置错误 | 将 `CORPORATE_ACTIONS_BASE_URL` 设为 `https://api.massive.com` |
| 运行中断 | 任意错误导致中断 | 直接重跑，已缓存日期自动跳过 |
| 分红抓取慢 | 数据量大，分页较多 | 正常现象，每页已设为 5000 条 |

---

*作者：Hyson L.*
