"""
Polymarket 市场扫描器
"""
import json
import requests
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class Market:
    """市场数据"""
    id: str
    question: str
    end_date: str
    outcome_prices: List[float]  # [YES_price, NO_price]
    volume: float
    liquidity: float
    fee: str
    clob_token_ids: List[str]
    closed: bool = False
    accepting_orders: bool = True
    start_date: str = ""  # 开始时间
    created_at: str = ""  # 创建时间
    
    @property
    def yes_price(self) -> float:
        try:
            return float(self.outcome_prices[0]) if len(self.outcome_prices) > 0 else 0.0
        except:
            return 0.0
    
    @property
    def no_price(self) -> float:
        try:
            return float(self.outcome_prices[1]) if len(self.outcome_prices) > 1 else 0.0
        except:
            return 0.0
    
    @property
    def hours_until_end(self) -> float:
        try:
            end_str = self.end_date
            if not end_str:
                return float('inf')
            # 移除 Z 或 +00:00
            end_str = end_str.replace('Z', '').replace('+00:00', '')
            end = datetime.fromisoformat(end_str)
            # 如果没有时区信息，假设是 UTC
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = end - now
            return delta.total_seconds() / 3600
        except:
            return float('inf')
    
    @property
    def max_probability(self) -> float:
        try:
            return float(max(self.yes_price, self.no_price))
        except:
            return 0.0
    
    @property
    def high_probability_outcome(self) -> str:
        return "YES" if self.yes_price >= self.no_price else "NO"
    
    @property
    def high_probability_price(self) -> float:
        return max(self.yes_price, self.no_price)


class MarketScanner:
    """市场扫描器"""
    
    def __init__(self):
        self.base_url = config.GAMMA_API_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; PolymarketScanner/1.0)'
        })
    
    def fetch_markets(self, limit: int = 500) -> List[Dict]:
        """获取市场列表 - 使用时间范围过滤"""
        now = datetime.now(timezone.utc)
        
        params = {
            'limit': limit,
            'closed': 'false',
            # 使用 API 的 end_date 参数过滤最近结束的市场
            'end_date_min': now.isoformat(),
            'end_date_max': (now + timedelta(hours=config.MAX_HOURS_UNTIL_END)).isoformat(),
        }
        
        try:
            response = self.session.get(
                f"{self.base_url}/markets",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            markets = response.json()
            
            # 客户端过滤：移除 crypto 相关市场
            crypto_keywords = ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'xrp', 'up or down']
            filtered = []
            for m in markets:
                question = m.get('question', '').lower()
                if not any(kw in question for kw in crypto_keywords):
                    filtered.append(m)
            
            logger.info(f"API返回 {len(markets)} 个市场，过滤crypto后 {len(filtered)} 个")
            return filtered
            
        except requests.RequestException as e:
            logger.error(f"获取市场列表失败: {e}")
            return []
    
    def parse_market(self, data: Dict) -> Optional[Market]:
        """解析市场数据"""
        try:
            # 解析价格
            outcome_prices = []
            if data.get('outcomePrices'):
                try:
                    outcome_prices = json.loads(data['outcomePrices'])
                except:
                    outcome_prices = []
            
            # 解析 token IDs
            clob_token_ids = []
            if data.get('clobTokenIds'):
                try:
                    clob_token_ids = json.loads(data['clobTokenIds'])
                except:
                    clob_token_ids = []
            
            # 处理布尔值 (API 可能返回字符串 "true" 或布尔值)
            def parse_bool(val):
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.lower() == 'true'
                return False
            
            return Market(
                id=data.get('id', ''),
                question=data.get('question', ''),
                end_date=data.get('endDate', ''),
                outcome_prices=outcome_prices,
                volume=float(data.get('volume', 0) or 0),
                liquidity=float(data.get('liquidity', 0) or 0),
                fee=data.get('fee', '0'),
                clob_token_ids=clob_token_ids,
                closed=parse_bool(data.get('closed')),
                accepting_orders=parse_bool(data.get('acceptingOrders', True)),
                start_date=data.get('startDate', ''),
                created_at=data.get('createdAt', '')
            )
        except Exception as e:
            logger.warning(f"解析市场数据失败: {e}")
            return None
    
    def filter_markets(self, markets: List[Market]) -> List[Market]:
        """筛选符合条件的市场"""
        filtered = []
        
        for market in markets:
            # 0. 检查市场是否已关闭或不再接受订单
            if market.closed or not market.accepting_orders:
                continue
            
            # 0. 检查市场是否已经结束
            if market.hours_until_end <= 0:
                continue
            
            # 1. 检查结束时间 <= 30天
            if market.hours_until_end > config.MAX_HOURS_UNTIL_END:
                continue
            
            # 2. 检查概率在 95-98% 之间
            if market.max_probability < config.MIN_PROBABILITY:
                continue
            if market.max_probability > config.MAX_PROBABILITY:
                continue
            
            # 3. 检查手续费
            try:
                fee = float(market.fee) if market.fee else 0
                if fee > config.MAX_FEE:
                    continue
            except:
                pass
            
            # 4. 检查交易量
            if market.volume < config.MIN_VOLUME:
                continue
            
            filtered.append(market)
            logger.info(f"符合条件: {market.question[:50]}... "
                       f"概率: {market.max_probability:.1%}, "
                       f"结束: {market.hours_until_end:.1f}小时后")
        
        # 排序：优先选择价格更低的（即概率更接近95%的，风险/收益比更好）
        filtered.sort(key=lambda m: m.high_probability_price)
        
        return filtered[:config.MAX_TRADES_PER_RUN]
    
    def scan(self) -> tuple:
        """扫描市场 - 返回 (filtered_markets, stats)"""
        logger.info("=" * 50)
        logger.info("开始扫描市场...")
        
        # 获取市场数据
        markets_data = self.fetch_markets()
        total_api = len(markets_data)
        logger.info(f"API返回 {total_api} 个市场")
        
        # 解析市场
        markets = []
        for data in markets_data:
            market = self.parse_market(data)
            if market:
                markets.append(market)
        
        logger.info(f"成功解析 {len(markets)} 个市场")
        
        # 筛选
        filtered = self.filter_markets(markets)
        non_crypto_count = len(markets)  # 过滤crypto后的数量（在fetch_markets里已经过滤了）
        
        stats = {
            'total_api': total_api,
            'total_parsed': len(markets),
            'non_crypto': non_crypto_count,
            'filtered': len(filtered)
        }
        
        logger.info(f"符合条件的市场: {len(filtered)} 个")
        
        return filtered[:config.MAX_TRADES_PER_RUN], stats
    
    def get_market_detail(self, market_id: str) -> Optional[Dict]:
        """获取市场详情"""
        try:
            response = self.session.get(
                f"{self.base_url}/markets/{market_id}",
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"获取市场详情失败: {e}")
            return None
    
    def check_settlements(self, trades_file: Path) -> dict:
        """检查待结算市场的结算状态"""
        import config
        
        if not trades_file.exists():
            return {'resolved': [], 'unresolved': [], 'newly_resolved': []}
        
        with open(trades_file, 'r') as f:
            data = json.load(f)
        
        # 收集所有未结算的交易
        all_trades = []
        for run in data.get('runs', []):
            for t in run.get('executed_trades', []):
                if not t.get('settled'):
                    all_trades.append(t)
        
        if not all_trades:
            return {'resolved': [], 'unresolved': [], 'newly_resolved': []}
        
        # 去重
        unique_markets = {}
        for t in all_trades:
            mid = t.get('market_id')
            if mid and mid not in unique_markets:
                unique_markets[mid] = t
        
        resolved = []
        unresolved = []
        newly_resolved = []
        
        # 逐个查询
        for mid, trade in unique_markets.items():
            try:
                response = self.session.get(f"{self.base_url}/markets/{mid}", timeout=10)
                market = response.json()
                
                is_closed = market.get('closed', False)
                resolution = market.get('resolution')
                
                if is_closed and resolution and str(resolution) != 'null':
                    result = {**trade, 'resolution': resolution, 'settled': True}
                    resolved.append(result)
                    if not trade.get('settled'):
                        newly_resolved.append(result)
                        logger.info(f"✅ 已结算: {trade.get('question')[:40]} → {resolution}")
                elif is_closed:
                    result = {**trade, 'resolution': 'CANCELLED', 'settled': True}
                    resolved.append(result)
                    if not trade.get('settled'):
                        newly_resolved.append(result)
                        logger.info(f"❌ 已关闭: {trade.get('question')[:40]}")
                else:
                    unresolved.append(trade)
            except Exception as e:
                logger.error(f"查询失败 {mid}: {e}")
                unresolved.append(trade)
        
        return {'resolved': resolved, 'unresolved': unresolved, 'newly_resolved': newly_resolved}


if __name__ == "__main__":
    # 测试
    scanner = MarketScanner()
    results = scanner.scan()
    for m in results:
        print(f"- {m.question[:60]}... (P={m.max_probability:.1%})")
