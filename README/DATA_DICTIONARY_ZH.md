# 数据字典

> 美股普通股市场数据

---

## 概览

| 文件 | 数据量 | 更新方式 | 说明 |
|------|--------|----------|------|
| `US_Share_Stock_Basic_All.parquet` | ~10,000 | 全量覆盖 | 股票基础信息 |
| `US_Share_Daily.parquet` | ~3M+ | 追加 | 原始日线行情 |
| `US_Share_Dividend.parquet` | ~50,000+ | 全量覆盖 | 分红事件 |
| `US_Share_Splits.parquet` | ~100–500 | 全量覆盖 | 拆股事件 |

**数据范围：** 2025-01-01 → 至今
**股票范围：** 仅美股普通股（CS）
**价格：** 所有价格均为美元原始未复权价格

---

## 1. US_Share_Stock_Basic_All.parquet

美股所有普通股的基础信息（含在市及已退市股票）。

| 列名 | 类型 | 说明 |
|------|------|------|
| `ticker` | string | 股票代码 |
| `name` | string | 公司全称 |
| `type` | string | 固定为 `CS`（普通股）|
| `active` | boolean | `True` 表示当前在市 |
| `currency_name` | string | 交易货币（如 `usd`） |
| `primary_exchange` | string | 主要交易所代码（如 `XNAS`、`XNYS`） |
| `composite_figi` | string | 彭博复合 FIGI 标识符 |
| `share_class_figi` | string | 彭博股票类别 FIGI |
| `cik` | string | SEC 注册号 |
| `sic_code` | string | SIC 行业代码 |
| `sic_description` | string | SIC 行业描述 |
| `list_date` | date | 上市日期 |
| `delisted_utc` | date | 退市日期（在市则为空） |
| `market_cap` | float | 市值（美元） |
| `weighted_shares_outstanding` | float | 加权流通股数 |
| `total_employees` | Int64 | 员工总数 |
| `homepage_url` | string | 公司官网地址 |

---

## 2. US_Share_Daily.parquet

2025年1月1日起所有普通股的原始（未复权）日线数据。

| 列名 | 类型 | 说明 |
|------|------|------|
| `date` | date | 交易日期 |
| `ticker` | string | 股票代码 |
| `open` | float | 开盘价（原始未复权） |
| `high` | float | 最高价（原始未复权） |
| `low` | float | 最低价（原始未复权） |
| `close` | float | 收盘价（原始未复权） |
| `volume` | float | 成交量（股数） |
| `vwap` | float | 成交量加权均价（VWAP） |
| `transactions` | Int64 | 成交笔数 |

> **注意：** 所有价格均为**原始未复权**价格。复权方法请参阅使用文档。

---

## 3. US_Share_Dividend.parquet

2025年1月1日起所有普通股的现金分红事件。

| 列名 | 类型 | 说明 |
|------|------|------|
| `ticker` | string | 股票代码 |
| `ex_dividend_date` | date | 除息日（定价关键日期） |
| `declaration_date` | date | 分红宣告日 |
| `record_date` | date | 股权登记日 |
| `pay_date` | date | 派息日 |
| `cash_amount` | float | 每股分红金额（美元） |
| `split_adjusted_cash_amount` | float | 经后续拆股调整后的每股分红 |
| `distribution_type` | string | 分红类型：`recurring` / `special` / `supplemental` / `irregular` / `unknown` |
| `frequency` | Int64 | 年度派息频率（0=一次性，1=年度，2=半年度，4=季度，12=月度） |
| `historical_adjustment_factor` | float | 仅含分红的累积后复权因子（由 Polygon 提供） |

> **关键字段：** `historical_adjustment_factor`
> 对日期 **D** 的原始价格进行分红复权时：
> 找到该 ticker 中 `ex_dividend_date > D` 的**第一条**记录，
> 则：`分红复权价 = 原始价格 × historical_adjustment_factor`

---

## 4. US_Share_Splits.parquet

2025年1月1日起所有普通股的拆股事件。

| 列名 | 类型 | 说明 |
|------|------|------|
| `ticker` | string | 股票代码 |
| `execution_date` | date | 拆股执行日期 |
| `adjustment_type` | string | 拆股类型：`forward_split`（正拆）/ `reverse_split`（反拆）/ `stock_dividend`（股票股息） |
| `split_from` | float | 拆股前股数（分母） |
| `split_to` | float | 拆股后股数（分子） |
| `historical_adjustment_factor` | float | 仅含拆股的累积后复权因子（由 Polygon 提供） |

> **关键字段：** `historical_adjustment_factor`
> 对日期 **D** 的原始价格进行拆股复权时：
> 找到该 ticker 中 `execution_date > D` 的**第一条**记录，
> 则：`拆股复权价 = 原始价格 × historical_adjustment_factor`

---

## 复权因子逻辑

完全后复权价格（拆股 + 分红）：

```
adj_price = raw_price × split_factor × div_factor
```

| 变量 | 来源 | 缺省值 |
|------|------|--------|
| `raw_price` | `US_Share_Daily.close` | — |
| `split_factor` | `US_Share_Splits.historical_adjustment_factor`（日期 D 之后的第一条拆股记录） | `1.0` |
| `div_factor` | `US_Share_Dividend.historical_adjustment_factor`（日期 D 之后的第一条分红记录） | `1.0` |
