"""
Polymarket 套利策略配置
"""
import os
from pathlib import Path

# 项目路径
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# API 配置
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# 交易配置
VIRTUAL_BALANCE = 1000.0  # 虚拟资金 $1000
MAX_TRADES_PER_RUN = 5   # 每次最多交易 5 个市场

# 筛选条件 - 优化版
MIN_PROBABILITY = 0.90   # 最小概率 90%
MAX_PROBABILITY = 0.98    # 最大概率 98% (在95-98%之间)
MAX_HOURS_UNTIL_END = 4   # 结束时间在 4 小时内

# 筛选条件
MIN_VOLUME = 1000         # 最小交易量
MAX_FEE = 0.0            # 最大手续费 (0 = 无手续费)

# 交易参数
TRADE_AMOUNT = 5        # 每个市场花费 $5 (最小)
MIN_PROFIT_MARGIN = 0.02 # 最小利润空间

# 文件路径
TRADES_FILE = DATA_DIR / "trades.json"
LOG_FILE = DATA_DIR / "scanner.log"

# 运行间隔 (秒)
SCAN_INTERVAL = 3600      # 1小时
