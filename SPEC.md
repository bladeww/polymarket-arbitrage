# Polymarket 套利策略 - 技术规格

## 1. 项目概述

- **策略名称**: 高概率预测买入策略
- **运行频率**: 每小时执行一次
- **虚拟资金**: $1000 USD
- **目标**: 扫描符合条件的市场，买入高概率预测

## 2. 筛选条件

1. **结束时间**: 距离结束 ≤ 1小时
2. **预测概率**: 某一边的 YES 或 NO ≥ 95%
3. **交易费用**: 无手续费或低手续费 (fee = 0 或 makerBaseFee = 0)
4. **选择数量**: 每次选择 5 个市场

## 3. 需要的 API

### 3.1 市场数据 API (公开，无需认证)
- **Base URL**: `https://gamma-api.polymarket.com`
- **端点**: `GET /markets`

**筛选参数**:
- `closed=false` - 只看开放市场
- `active=true` - 活跃市场
- `end_date_max` - 结束时间上限
- `volume_num_min` - 最小交易量

### 3.2 订单簿 API (可选，用于更精确的价格)
- **Base URL**: `https://clob.polymarket.com`
- **端点**: `GET /book?token_id={token_id}`

## 4. 数据结构

### 4.1 市场信息 (from API)
```json
{
  "id": "market_id",
  "question": "Will X happen?",
  "endDate": "2026-02-16T17:00:00Z",
  "outcomePrices": "[\"0.96\", \"0.04\"]",  // YES, NO
  "volume": "50000",
  "fee": "0.02",
  "liquidity": "10000",
  "clobTokenIds": "[\"token1\", \"token2\"]"
}
```

### 4.2 交易记录
```json
{
  "timestamp": "2026-02-16T12:00:00Z",
  "run_id": "uuid",
  "virtual_balance": 1000,
  "planned_trades": [
    {
      "market_id": "...",
      "question": "...",
      "outcome": "YES",
      "price": 0.96,
      "amount": 20,
      "reason": "Probability 96% >= 95%, ends in 30min"
    }
  ],
  "executed_trades": [
    // 实际执行的交易
  ],
  "summary": {
    "total_markets_scanned": 100,
    "markets_matching_criteria": 5,
    "trades_executed": 5,
    "total_invested": 100,
    "potential_payout": 100
  }
}
```

## 5. 文件结构

```
polymarket-arbitrage/
├── config.py              # 配置文件
├── scanner.py            # 市场扫描器
├── trader.py             # 交易执行器
├── recorder.py           # 交易记录器
├── main.py               # 主程序入口
├── trades.json           # 交易记录 (自动生成)
└── requirements.txt      # Python 依赖
```

## 6. 待确认事项

1. **API Token**: 是否需要 Polymarket API key？（目前看来公开 API 无需认证）
2. **交易执行**: 
   - 方案 A: 只做模拟交易 (paper trading)
   - 方案 B: 需要 private API 进行真实交易（需要 API key）
3. **运行方式**: 
   - 方案 A: 本地定时运行 (cron)
   - 方案 B: 集成到 OpenClaw 作为 cron job

请确认以上问题，我开始写代码。
