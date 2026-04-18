# 使用文档

> 美股普通股数据管道

---

## 1. 环境配置

### 依赖安装

```bash
pip install -r requirements.txt
```

### 配置 API Key

打开 `config.py`，填入你的 API Key：

```python
POLYGON_API_KEY            = "your_polygon_key_here"   # 日线数据
CORPORATE_ACTIONS_BASE_URL = "https://api.massive.com" # 分红与拆股
```

### 项目结构

```
BarFlow/
├── config.py               # 所有参数
├── main.py                 # 首次全量运行
├── daily_update.py         # 每日增量更新
├── fetch_stock_basic.py
├── fetch_daily.py
├── fetch_dividends.py
├── fetch_splits.py
├── utils.py
├── raw_daily_cache/        # 每日缓存
└── output/                 # 最终输出文件
    ├── US_Share_Stock_Basic_All.parquet
    ├── US_Share_Daily.parquet
    ├── US_Share_Dividend.parquet
    └── US_Share_Splits.parquet
```

---

## 2. 运行数据管道

### 首次全量运行

运行一次，下载从 `START_DATE`（默认 2025-01-01）至昨日的全量数据。

```bash
python main.py
```

按顺序执行 4 个步骤：
1. 抓取所有普通股基础信息
2. 逐日下载行情（含断点续传）
3. 下载分红历史
4. 下载拆股历史

> **注意：** 步骤2需抓取约330个交易日，免费版限速5次/分钟，首次运行约需70分钟。
> 中途中断后直接重跑即可，已缓存的日期自动跳过。

### 每日增量更新

每个交易日运行一次（例如收盘后通过 cron 定时执行）：

```bash
python daily_update.py
```

每次运行内容：

| 步骤 | 操作 |
|------|------|
| 1 | 刷新股票列表，记录新增/退市 |
| 2 | 追加昨日行情（自动补缺） |
| 3 | 全量覆盖分红文件 |
| 4 | 全量覆盖拆股文件 |

### 其他运行模式

```bash
# 仅追加日线数据（最快，约1分钟）
python main.py --daily-only

# 仅刷新分红和拆股数据
python main.py --corporate-only
```

---

## 3. 读取数据

```python
import pandas as pd

daily    = pd.read_parquet("output/US_Share_Daily.parquet")
basic    = pd.read_parquet("output/US_Share_Stock_Basic_All.parquet")
dividend = pd.read_parquet("output/US_Share_Dividend.parquet")
splits   = pd.read_parquet("output/US_Share_Splits.parquet")
```

---

## 4. 计算复权价格

后复权价格公式：

```
adj_price = raw_price × split_factor × div_factor
```

若日期 D 之后无对应事件，因子默认为 1.0。

### 完整示例

```python
import pandas as pd
import numpy as np

daily    = pd.read_parquet("output/US_Share_Daily.parquet")
dividend = pd.read_parquet("output/US_Share_Dividend.parquet")
splits   = pd.read_parquet("output/US_Share_Splits.parquet")

def get_adj_close(ticker: str) -> pd.DataFrame:
    """返回指定股票的后复权收盘价。"""
    df = daily[daily["ticker"] == ticker][["date", "close"]].copy()

    # ── 拆股因子 ──────────────────────────────────────────
    t_splits = splits[splits["ticker"] == ticker].sort_values("execution_date")

    def get_split_factor(date):
        future = t_splits[t_splits["execution_date"] > date]
        return future.iloc[0]["historical_adjustment_factor"] if not future.empty else 1.0

    # ── 分红因子 ───────────────────────────────────────────
    t_divs = dividend[dividend["ticker"] == ticker].sort_values("ex_dividend_date")

    def get_div_factor(date):
        future = t_divs[t_divs["ex_dividend_date"] > date]
        return future.iloc[0]["historical_adjustment_factor"] if not future.empty else 1.0

    df["split_factor"] = df["date"].apply(get_split_factor)
    df["div_factor"]   = df["date"].apply(get_div_factor)
    df["adj_close"]    = df["close"] * df["split_factor"] * df["div_factor"]

    return df[["date", "close", "adj_close"]]

# 用法
aapl = get_adj_close("AAPL")
print(aapl.tail())
```

### 向量化版本（更快）

```python
def get_adj_close_fast(ticker: str) -> pd.DataFrame:
    df = daily[daily["ticker"] == ticker][["date", "close"]].copy().sort_values("date")

    t_splits = (
        splits[splits["ticker"] == ticker]
        [["execution_date", "historical_adjustment_factor"]]
        .rename(columns={"execution_date": "date",
                         "historical_adjustment_factor": "split_factor"})
        .sort_values("date")
    )
    t_divs = (
        dividend[dividend["ticker"] == ticker]
        [["ex_dividend_date", "historical_adjustment_factor"]]
        .rename(columns={"ex_dividend_date": "date",
                         "historical_adjustment_factor": "div_factor"})
        .sort_values("date")
    )

    # 对每个价格日期，找到严格晚于该日期的第一个事件日期
    df = pd.merge_asof(df, t_splits, on="date", direction="forward").fillna({"split_factor": 1.0})
    df = pd.merge_asof(df, t_divs,   on="date", direction="forward").fillna({"div_factor":   1.0})
    df["adj_close"] = df["close"] * df["split_factor"] * df["div_factor"]

    return df[["date", "close", "adj_close", "split_factor", "div_factor"]]
```

---

## 5. 常用查询

### 按交易所筛选

```python
# 仅纳斯达克
nasdaq = basic[basic["primary_exchange"] == "XNAS"]["ticker"].tolist()

# 仅纽交所
nyse = basic[basic["primary_exchange"] == "XNYS"]["ticker"].tolist()
```

### 按日期范围筛选

```python
mask = (daily["date"] >= pd.to_datetime("2025-06-01").date()) & \
       (daily["date"] <= pd.to_datetime("2025-12-31").date())
h2_2025 = daily[mask]
```

### 获取当前在市股票

```python
active_tickers = basic[basic["active"] == True]["ticker"].tolist()
```

### 股息率

```python
# 某股票的年化股息率
ticker = "AAPL"
latest_price  = daily[daily["ticker"] == ticker].sort_values("date").iloc[-1]["close"]
annual_div    = dividend[dividend["ticker"] == ticker]["cash_amount"].sum()
div_yield     = annual_div / latest_price
print(f"{ticker} dividend yield: {div_yield:.2%}")
```

### 查找发生拆股的股票

```python
# 数据范围内所有正拆股票
forward_splits = splits[splits["adjustment_type"] == "forward_split"]
print(forward_splits[["ticker", "execution_date", "split_from", "split_to"]])
```

---

## 6. 配置参数说明

所有参数均在 `config.py` 中，主要配置项：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `POLYGON_API_KEY` | — | 日线数据 API Key |
| `CORPORATE_ACTIONS_BASE_URL` | `https://api.massive.com` | 分红/拆股数据 API 地址 |
| `START_DATE` | `2025-01-01` | 数据起始日期 |
| `END_DATE` | 昨日 | 数据截止日期（默认昨日） |
| `TICKER_TYPE` | `CS` | 股票类型过滤 |
| `RATE_LIMIT_CALLS` | `5` | 限速：每窗口最大调用次数 |
| `RATE_LIMIT_PERIOD` | `60` | 限速窗口（秒） |
| `FORCE_REFRESH_STOCK_BASIC` | `False` | 强制重新抓取股票基础信息 |

---

## 7. 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 当日数据 403 | 免费版无法访问当日数据 | 已修复，END_DATE 默认为昨日 |
| 任意日期 403 | API Key 错误或未填写 | 检查 `config.py` 中的 `POLYGON_API_KEY` |
| 分红/拆股 404 | CORPORATE_ACTIONS_BASE_URL 配置错误 | 设置为 `https://api.massive.com` |
| 运行中断 | 任意错误导致中断 | 直接重跑，已缓存日期自动跳过 |
| 分红抓取慢 | 数据量大，分页较多 | 正常现象，每页已设为 5000 条 |
