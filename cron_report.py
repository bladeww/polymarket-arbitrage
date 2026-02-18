#!/usr/bin/env python3
"""Cron 任务报告脚本 - 包含结算状态"""
import json
import requests
import sys
from pathlib import Path

API_URL = "https://gamma-api.polymarket.com/markets"
TRADES_FILE = Path("data/trades.json")

def check_settlements():
    """检查结算状态"""
    if not TRADES_FILE.exists():
        return {'resolved': [], 'unresolved': [], 'newly_resolved': []}
    
    with open(TRADES_FILE) as f:
        data = json.load(f)
    
    # 收集未结算交易
    all_trades = []
    for run in data.get('runs', []):
        for t in run.get('executed_trades', []):
            if not t.get('settled'):
                all_trades.append(t)
    
    if not all_trades:
        return {'resolved': [], 'unresolved': [], 'newly_resolved': []}
    
    # 去重
    unique = {}
    for t in all_trades:
        mid = t.get('market_id')
        if mid and mid not in unique:
            unique[mid] = t
    
    resolved = []
    unresolved = []
    newly = []
    
    for mid, trade in unique.items():
        try:
            resp = requests.get(f"{API_URL}/{mid}", timeout=10)
            m = resp.json()
            if m.get('closed'):
                res = m.get('resolution')
                if res and str(res) != 'null':
                    resolved.append({**trade, 'resolution': res})
                    if not trade.get('settled'):
                        newly.append({**trade, 'resolution': res})
                else:
                    resolved.append({**trade, 'resolution': 'CANCELLED'})
                    if not trade.get('settled'):
                        newly.append({**trade, 'resolution': 'CANCELLED'})
            else:
                unresolved.append(trade)
        except:
            unresolved.append(trade)
    
    return {'resolved': resolved, 'unresolved': unresolved, 'newly_resolved': newly}

# 加载数据
with open(TRADES_FILE) as f:
    d = json.load(f)

runs = d.get('runs', [])
if not runs:
    print("暂无交易记录")
    sys.exit(0)

# 最新扫描
latest = runs[-1]
scan = latest.get('scan_info', {})
summary = latest.get('summary', {})

# 结算状态
settlement = check_settlements()

# 构建消息
msg = f"""📊 Polymarket 扫描报告
━━━━━━━━━━━━━━━━
🔍 扫描结果:
   API返回: {scan.get('total_api', 0)} 市场
   符合条件: {scan.get('filtered', 0)} 个

💰 钱包状态:
   余额: ${summary.get('balance_after', 0):.2f}
   本次投入: ${summary.get('total_invested', 0):.2f}
   潜在回报: ${summary.get('potential_payout', 0):.2f}"""

# 结算结果
if settlement['newly_resolved']:
    msg += f"""\n\n🎯 结算结果 ({len(settlement['newly_resolved'])}笔):"""
    for r in settlement['newly_resolved']:
        res = r.get('resolution', 'UNKNOWN')
        outcome = r.get('outcome', '')
        win = '✅' if (outcome == 'YES' and res == 'Yes') or (outcome == 'NO' and res == 'No') else '❌'
        msg += f"""\n   {win} {outcome} → {res}"""

# 待结算
unresolved = len(settlement['unresolved'])
if unresolved > 0:
    msg += f"""\n\n⏳ 待结算 ({unresolved}笔):"""
    for u in settlement['unresolved'][:3]:
        msg += f"""\n   {u.get('outcome')} @ ${u.get('price')} - {u.get('question', '')[:25]}..."""

print(msg)
