"""
Polymarket 套利策略主程序
每1小时扫描市场，执行符合条件的交易
"""
import json
import time
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from scanner import MarketScanner
from trader import VirtualTrader, TradeRecorder, PlannedTrade, ExecutedTrade

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ArbitrageBot:
    """套利机器人"""
    
    def __init__(self):
        self.scanner = MarketScanner()
        self.trader = VirtualTrader(config.VIRTUAL_BALANCE)
        self.recorder = TradeRecorder()
        self.running = True
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理退出信号"""
        logger.info("收到退出信号，正在停止...")
        self.running = False
    
    def run_once(self) -> dict:
        """执行一次扫描和交易"""
        logger.info("=" * 60)
        logger.info(f"开始扫描 - {datetime.now(timezone.utc).isoformat()}")
        
        # 0. 检查待结算市场
        settlement = self.scanner.check_settlements(config.DATA_DIR / "trades.json")
        if settlement.get('newly_resolved'):
            logger.info(f"📊 发现 {len(settlement['newly_resolved'])} 个新结算市场")
            # TODO: 更新交易记录中的结算状态
        
        logger.info(f"虚拟余额: ${self.trader.get_balance():.2f}")
        
        balance_before = self.trader.get_balance()
        
        # 1. 扫描市场
        markets, scan_stats = self.scanner.scan()
        
        # 保存扫描统计
        scan_info = {
            'total_api': scan_stats.get('total_api', 0),
            'total_parsed': scan_stats.get('total_parsed', 0),
            'non_crypto': scan_stats.get('non_crypto', 0),
            'filtered': scan_stats.get('filtered', 0)
        }
        
        if not markets:
            logger.info("没有找到符合条件的市场")
            return {
                'status': 'no_markets',
                'balance_before': balance_before,
                'balance_after': balance_before,
                'planned_trades': [],
                'executed_trades': [],
                'scan_info': scan_info
            }
        
        # 2. 创建计划交易
        planned_trades = []
        for market in markets:
            trade = PlannedTrade(
                market_id=market.id,
                question=market.question,
                outcome=market.high_probability_outcome,
                price=market.high_probability_price,
                amount=config.TRADE_AMOUNT,
                reason=f"概率 {market.max_probability:.1%}, "
                       f"结束时间 {market.hours_until_end:.1f}小时后, "
                       f"手续费 {market.fee}"
            )
            planned_trades.append(trade.to_dict())
        
        # 3. 执行交易
        executed_trades = []
        for market in markets:
            # 检查余额
            if self.trader.get_balance() < config.TRADE_AMOUNT:
                logger.warning("余额不足，跳过交易")
                break
            
            # 执行交易
            executed = self.trader.execute_trade(market)
            if executed:
                executed_trades.append(executed.to_dict())
                logger.info(f"✓ 执行交易: {executed.outcome} "
                           f"${executed.amount} @ ${executed.price:.2f} "
                           f"- {executed.question[:40]}...")
            else:
                logger.warning(f"✗ 交易失败: {market.question[:40]}...")
        
        # 4. 记录结果
        balance_after = self.trader.get_balance()
        
        run_data = {
            'balance_before': balance_before,
            'balance_after': balance_after,
            'planned_trades': planned_trades,
            'executed_trades': executed_trades,
            'scan_info': scan_info,
            'summary': {
                'markets_scanned': len(markets),
                'trades_planned': len(planned_trades),
                'trades_executed': len(executed_trades),
                'total_invested': self.trader.get_total_invested(),
                'potential_payout': self.trader.get_potential_payout(),
                'balance_after': balance_after
            }
        }
        
        # 保存到记录
        self.recorder.record_run(run_data)
        
        logger.info(f"完成 - 余额: ${balance_after:.2f}, "
                   f"花费: ${self.trader.get_total_invested():.2f}, "
                   f"潜在回报: ${self.trader.get_potential_payout():.2f}, "
                   f"潜在利润: ${self.trader.get_total_profit_if_win():.2f}")
        
        return run_data
    
    def run_loop(self):
        """循环运行"""
        logger.info("=" * 60)
        logger.info("Polymarket 套利机器人启动")
        logger.info(f"虚拟余额: ${config.VIRTUAL_BALANCE}")
        logger.info(f"扫描间隔: {config.SCAN_INTERVAL}秒")
        logger.info(f"筛选条件: 结束时间≤{config.MAX_HOURS_UNTIL_END}小时, "
                   f"概率≥{config.MIN_PROBABILITY:.0%}, "
                   f"手续费≤{config.MAX_FEE}")
        logger.info("=" * 60)
        
        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"运行错误: {e}", exc_info=True)
            
            # 等待下一次扫描
            logger.info(f"等待 {config.SCAN_INTERVAL} 秒...")
            for _ in range(config.SCAN_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)
        
        logger.info("机器人已停止")


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Polymarket 套利机器人')
    parser.add_argument('--once', '-o', action='store_true',
                       help='只运行一次（不循环）')
    parser.add_argument('--balance', '-b', type=float,
                       default=config.VIRTUAL_BALANCE,
                       help='虚拟余额')
    args = parser.parse_args()
    
    # 创建机器人
    bot = ArbitrageBot()
    bot.trader = VirtualTrader(args.balance)
    
    if args.once:
        # 只运行一次
        bot.run_once()
    else:
        # 循环运行
        bot.run_loop()


if __name__ == "__main__":
    main()
