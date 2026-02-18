"""
Polymarket 交易模拟器
"""
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from scanner import Market, MarketScanner
import config


@dataclass
class PlannedTrade:
    """计划交易"""
    market_id: str
    question: str
    outcome: str  # YES or NO
    price: float
    amount: float
    reason: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ExecutedTrade:
    """已执行交易"""
    market_id: str
    question: str
    outcome: str  # YES or NO
    price: float  # 买入价格 (0-1)
    amount: float  # 股数
    cost: float   # 实际花费 (price × amount)
    timestamp: str
    status: str  # success, failed, simulated
    start_date: str = ""  # 市场开始时间
    end_date: str = ""    # 市场结束时间
    created_at: str = ""  # 市场创建时间
    
    def to_dict(self):
        return asdict(self)


class VirtualTrader:
    """虚拟交易器"""
    
    def __init__(self, initial_balance: float = config.VIRTUAL_BALANCE):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions = []  # 持仓
        self.trade_history = []  # 交易历史
    
    def calculate_payout(self, trade: PlannedTrade) -> float:
        """计算潜在收益"""
        # Polymarket 机制：
        # - 买入 YES: 花费 price × amount，得到 amount 的 YES 股
        # - 买入 NO: 花费 price × amount，得到 amount 的 NO 股
        # - 正确时：每股票获得 $1.0
        # - 收益 = 股票价值 - 成本 = amount × 1.0 - (price × amount)
        # - 收益 = amount × (1.0 - price)
        
        if trade.outcome == "YES":
            # 买入 YES，正确则获得 (1 - price) × amount
            return trade.amount * (1.0 - trade.price)
        else:
            # 买入 NO，正确则获得 (1 - price) × amount
            return trade.amount * (1.0 - trade.price)
    
    def execute_trade(self, market: Market, amount: float = None) -> Optional[ExecutedTrade]:
        """执行交易（虚拟）"""
        if amount is None:
            amount = config.TRADE_AMOUNT
        
        # 决定买入 YES 还是 NO (买入高概率一边)
        outcome = market.high_probability_outcome
        price = market.high_probability_price
        
        # Polymarket 机制:
        # - 价格 p 表示概率
        # - 花费 $X 可以买到 $X/p 的股票
        # - 如果正确，每股票价值 $1
        # - 所以: 花费 cost，得到 cost/p 的股票，如果正确获得 cost/p
        
        # 我们的策略是: 投入固定金额 (TRADE_AMOUNT)
        # 所以: cost = TRADE_AMOUNT
        # 股数 = cost / price
        
        # 固定买 SHARES_COUNT 份
        shares_count = 5  # 固定买5份
        cost = price * shares_count  # 花费 = 价格 × 股数
        shares = cost / price  # 能买到的股数
        
        # 检查余额
        if self.balance < cost:
            return None
        
        # 模拟交易
        trade = ExecutedTrade(
            market_id=market.id,
            question=market.question,
            outcome=outcome,
            price=price,
            amount=shares,  # 股数
            cost=cost,      # 实际花费
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="simulated",
            start_date=market.start_date,
            end_date=market.end_date,
            created_at=market.created_at
        )
        
        # 更新余额
        self.balance -= cost
        
        # 记录持仓
        self.positions.append({
            'market_id': market.id,
            'question': market.question,
            'outcome': outcome,
            'price': price,
            'shares': shares,
            'cost': cost,
            'potential_payout': shares,  # 如果正确，获得 shares × $1
            'profit_if_win': shares - cost,  # 利润
            'timestamp': trade.timestamp
        })
        
        self.trade_history.append(trade)
        
        return trade
    
    def get_balance(self) -> float:
        return self.balance
    
    def get_total_invested(self) -> float:
        return sum(p['cost'] for p in self.positions)
    
    def get_potential_payout(self) -> float:
        return sum(p['potential_payout'] for p in self.positions)
    
    def get_total_profit_if_win(self) -> float:
        return sum(p['profit_if_win'] for p in self.positions)


class TradeRecorder:
    """交易记录器"""
    
    def __init__(self, filepath=config.TRADES_FILE):
        self.filepath = filepath
        self.trades = self._load()
    
    def _load(self) -> Dict:
        """加载历史记录"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'runs': [],
            'total_invested': 0,
            'total_payout': 0,
            'win_count': 0,
            'loss_count': 0
        }
    
    def _save(self):
        """保存记录"""
        with open(self.filepath, 'w') as f:
            json.dump(self.trades, f, indent=2, ensure_ascii=False)
    
    def record_run(self, run_data: Dict):
        """记录一次运行"""
        run_id = str(uuid.uuid4())[:8]
        
        run_record = {
            'run_id': run_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'virtual_balance_before': run_data.get('balance_before', 0),
            'planned_trades': run_data.get('planned_trades', []),
            'executed_trades': run_data.get('executed_trades', []),
            'scan_info': run_data.get('scan_info', {}),
            'summary': run_data.get('summary', {})
        }
        
        self.trades['runs'].append(run_record)
        
        # 更新统计
        executed = run_data.get('executed_trades', [])
        if executed:
            self.trades['total_invested'] += sum(t['amount'] for t in executed)
        
        self._save()
        
        logger.info(f"Run {run_id} 已记录")
        return run_id
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_runs': len(self.trades['runs']),
            'total_invested': self.trades['total_invested'],
            'total_payout': self.trades['total_payout'],
            'win_count': self.trades['win_count'],
            'loss_count': self.trades['loss_count']
        }


# 配置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # 测试
    scanner = MarketScanner()
    trader = VirtualTrader(1000)
    recorder = TradeRecorder()
    
    # 扫描
    markets = scanner.scan()
    
    print(f"\n找到 {len(markets)} 个符合条件的市场")
    print(f"虚拟余额: ${trader.get_balance():.2f}")
    
    # 执行交易
    for market in markets[:5]:
        trade = trader.execute_trade(market)
        if trade:
            print(f"✓ 买入 {trade.outcome} ${trade.amount} @ {trade.price:.2f}")
    
    print(f"\n交易后余额: ${trader.get_balance():.2f}")
    print(f"总投资: ${trader.get_total_invested():.2f}")
    print(f"潜在收益: ${trader.get_potential_payout():.2f}")
