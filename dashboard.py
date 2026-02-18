"""
Polymarket 套利策略 - Web 仪表板 (完整版)
"""
import json
import http.server
import socketserver
from pathlib import Path
import config
from datetime import datetime, timezone

PORT = 80
TRADES_FILE = config.DATA_DIR / "trades.json"

def load_data():
    if TRADES_FILE.exists():
        with open(TRADES_FILE, 'r') as f:
            return json.load(f)
    return {"runs": []}

def calculate_stats(data):
    runs = data.get('runs', [])
    
    all_trades = [t for run in runs for t in run.get('executed_trades', [])]
    
    # 分类统计
    pending_trades = [t for t in all_trades if not t.get('settled')]
    cancelled_trades = [t for t in all_trades if t.get('resolution') == 'CANCELLED']
    settled_trades = [t for t in all_trades if t.get('settled') and t.get('resolution') != 'CANCELLED']
    
    pending_cost = sum(t.get('cost', 0) for t in pending_trades)
    pending_payout = sum(t.get('amount', 0) for t in pending_trades)  # 股数
    cancelled_cost = sum(t.get('cost', 0) for t in cancelled_trades)
    
    # 当前余额 = 虚拟余额 - 待结算投入 (取消的已退款)
    actual_balance = config.VIRTUAL_BALANCE - pending_cost
    
    # 潜在利润 = 待结算的潜在回报 - 待结算投入
    potential_profit = pending_payout - pending_cost
    
    # 实际盈利（已结算赢的）
    actual_profit = sum(t.get('profit', 0) for t in settled_trades if t.get('profit', 0) > 0)
    
    # ROI = 潜在利润 / 待结算投入
    roi = (potential_profit / pending_cost * 100) if pending_cost > 0 else 0
    
    return {
        'balance': actual_balance,
        'total_invested': sum(t.get('cost', 0) for t in all_trades),
        'pending_cost': pending_cost,
        'cancelled_cost': cancelled_cost,
        'potential_payout': pending_payout,
        'potential_profit': potential_profit,
        'actual_profit': actual_profit,
        'total_runs': len(runs),
        'total_trades': len(all_trades),
        'settled': len(settled_trades),
        'cancelled': len(cancelled_trades),
        'pending': len(pending_trades),
        'roi': roi
    }

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        
        if path == '/' or path == '/index.html':
            # 获取查询参数
            from urllib.parse import parse_qs
            query = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
            
            # 筛选日期
            date_filter = query.get('date', [''])[0]
            
            data = load_data()
            stats = calculate_stats(data)
            runs = data.get('runs', [])
            
            # 日期筛选
            if date_filter:
                filtered_runs = [r for r in runs if r.get('timestamp', '').startswith(date_filter)]
            else:
                filtered_runs = runs
            
            html = self.generate_html(stats, filtered_runs)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def generate_html(self, stats, runs):
        # 生成日期选项
        dates = sorted(set(r.get('timestamp', '')[:10] for r in runs if r.get('timestamp')), reverse=True)
        
        html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket 套利策略监控</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial; background: #0f0f23; color: #fff; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        
        h1 {{ text-align: center; margin-bottom: 20px; color: #4ade80; }}
        h2 {{ margin: 25px 0 15px; padding-bottom: 10px; border-bottom: 1px solid #333; }}
        
        /* 搜索表单 */
        .search-box {{ background: #1a1a3e; padding: 15px; border-radius: 10px; margin-bottom: 20px; }}
        .search-box input, .search-box button {{ padding: 10px; border-radius: 5px; border: none; }}
        .search-box input {{ background: #2a2a4e; color: #fff; width: 200px; }}
        .search-box button {{ background: #4ade80; color: #000; cursor: pointer; margin-left: 10px; }}
        
        /* 统计卡片 */
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .stat-card {{ background: #1a1a3e; padding: 20px; border-radius: 10px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; margin: 10px 0; }}
        .stat-label {{ color: #888; font-size: 12px; }}
        .positive {{ color: #4ade80; }}
        
        /* 交易记录 */
        .run-item {{ background: #1a1a3e; border-radius: 10px; margin-bottom: 20px; overflow: hidden; }}
        .run-header {{ background: #2a2a5e; padding: 15px; display: flex; justify-content: space-between; align-items: center; }}
        .run-time {{ color: #4ade80; }}
        .run-stats {{ color: #888; font-size: 14px; }}
        
        /* 市场表格 */
        .market-table {{ width: 100%; border-collapse: collapse; }}
        .market-table th, .market-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #333; }}
        .market-table th {{ background: #252545; color: #888; font-weight: normal; font-size: 12px; }}
        .market-table tr:hover {{ background: #1a1a3e; }}
        
        .price {{ font-weight: bold; }}
        .price-high {{ color: #4ade80; }}
        .price-low {{ color: #f87171; }}
        
        .outcome {{ padding: 3px 10px; border-radius: 3px; font-size: 12px; font-weight: bold; }}
        .outcome-YES {{ background: #4ade80; color: #000; }}
        .outcome-NO {{ background: #f87171; color: #000; }}
        
        .section-markets {{ padding: 15px; }}
        .section-trades {{ padding: 15px; }}
        
        .filter-info {{ background: #252545; padding: 10px 15px; margin: 10px 15px; border-radius: 5px; font-size: 13px; color: #888; }}
        
        /* 日期导航 */
        .date-nav {{ display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }}
        .date-btn {{ padding: 8px 16px; background: #1a1a3e; color: #fff; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; }}
        .date-btn:hover, .date-btn.active {{ background: #4ade80; color: #000; }}
        
        .refresh {{ text-align: center; margin-top: 30px; }}
        .refresh a {{ color: #4ade80; text-decoration: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Polymarket 套利策略监控</h1>
        
        <!-- 钱包状态 -->
        <h2>💰 钱包状态</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">虚拟余额</div>
                <div class="stat-value">${stats['balance']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">总投入</div>
                <div class="stat-value">${stats['total_invested']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">待结算</div>
                <div class="stat-value" style="color:#fbbf24">${stats['pending_cost']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">已退款</div>
                <div class="stat-value">${stats['cancelled_cost']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">潜在回报</div>
                <div class="stat-value positive">${stats['potential_payout']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">潜在利润</div>
                <div class="stat-value positive">${stats['potential_profit']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">运行次数</div>
                <div class="stat-value">{stats['total_runs']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">交易笔数</div>
                <div class="stat-value">{stats['total_trades']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">待/取消/已结</div>
                <div class="stat-value">{stats['pending']}/{stats['cancelled']}/{stats['settled']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">实际盈利</div>
                <div class="stat-value">${stats['actual_profit']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">ROI</div>
                <div class="stat-value positive">{stats['roi']:.2f}%</div>
            </div>
        </div>
        
        <!-- 日期筛选 -->
        <h2>📅 历史记录</h2>
        <div class="date-nav">
            <a href="/" class="date-btn">全部</a>
'''
        
        for d in dates[:10]:
            html += f'            <a href="/?date={d}" class="date-btn">{d}</a>\n'
        
        html += '''        </div>
'''
        
        # 按时间倒序显示每次搜索结果
        for run in reversed(runs):
            timestamp = run.get('timestamp', '')
            summary = run.get('summary', {})
            planned = run.get('planned_trades', [])
            executed = run.get('executed_trades', [])
            
            # 格式化时间
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                local_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                local_time = timestamp
            
            # 扫描统计
            scan_info = run.get('scan_info', {})
            
            html += f'''
        <div class="run-item">
            <div class="run-header">
                <div class="run-time">🕐 {local_time}</div>
                <div class="run-stats">
                    API返回 {scan_info.get('total_api', 0)} 市场 | 
                    过滤crypto后 {scan_info.get('non_crypto', 0)} | 
                    符合条件 {scan_info.get('filtered', 0)} 个
                </div>
            </div>
'''
            
            # 搜索结果
            if planned:
                html += f'''
            <div class="filter-info">
                筛选条件: 结束时间≤{config.MAX_HOURS_UNTIL_END}小时, 概率{config.MIN_PROBABILITY*100:.0f}-{config.MAX_PROBABILITY*100:.0f}%, 
                交易量>$50K, 流动性>$10K, 创建时间>1小时
            </div>
            <div class="section-markets">
                <h3>🔍 搜索结果 (符合条件 {len(planned)} 个)</h3>
                <table class="market-table">
                    <tr>
                        <th>交易</th>
                        <th>名称</th>
                        <th>价格</th>
                        <th>概率</th>
                        <th>Market ID</th>
                    </tr>
'''
                for p in planned[:5]:
                    outcome = p.get('outcome', '')
                    price = p.get('price', 0)
                    prob = price * 100
                    question = p.get('question', '')[:50]
                    market_id = p.get('market_id', '')
                    
                    html += f'''                    <tr>
                        <td><span class="outcome outcome-{outcome}">{outcome}</span></td>
                        <td>{question}</td>
                        <td class="price price-{outcome}">${price:.4f}</td>
                        <td>{prob:.1f}%</td>
                        <td>{market_id}</td>
                    </tr>
'''
                html += '''                </table>
            </div>
'''
            
            # 执行交易
            if executed:
                html += f'''
            <div class="section-trades">
                <h3>📋 执行交易 ({len(executed)} 笔)</h3>
                <table class="market-table">
                    <tr>
                        <th>交易</th>
                        <th>名称</th>
                        <th>买入价</th>
                        <th>股数</th>
                        <th>花费</th>
                        <th>创建时间</th>
                        <th>结束时间</th>
                        <th>状态</th>
                    </tr>
'''
                for t in executed:
                    outcome = t.get('outcome', '')
                    price = t.get('price', 0)
                    amount = t.get('amount', 0)
                    cost = t.get('cost', 0)
                    question = t.get('question', '')[:35]
                    end_date = t.get('end_date', '')[:16].replace('T', ' ')
                    created_at = t.get('created_at', '')[:16].replace('T', ' ') if t.get('created_at') else ''
                    settled = t.get('settled', False)
                    resolution = t.get('resolution', '')
                    
                    # 结算状态
                    if settled:
                        if resolution == 'CANCELLED':
                            status = '<span style="color:#f87171">已取消</span>'
                        else:
                            win = (outcome == 'YES' and resolution == 'Yes') or (outcome == 'NO' and resolution == 'No')
                            status = '<span style="color:#4ade80">✅赢</span>' if win else '<span style="color:#f87171">❌输</span>'
                    else:
                        status = '<span style="color:#888">⏳待结算</span>'
                    
                    html += f'''                    <tr>
                        <td><span class="outcome outcome-{outcome}">{outcome}</span></td>
                        <td>{question}</td>
                        <td>${price:.4f}</td>
                        <td>{amount:.2f}</td>
                        <td>${cost:.2f}</td>
                        <td>{created_at}</td>
                        <td>{end_date}</td>
                        <td>{status}</td>
                    </tr>
'''
                html += '''                </table>
            </div>
'''
            
            html += '''        </div>
'''
        
        html += '''
        <div class="refresh">
            <a href="/">🔄 刷新页面</a>
        </div>
    </div>
</body>
</html>'''
        return html

if __name__ == '__main__':
    print(f"Server: http://localhost:{PORT}")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()
