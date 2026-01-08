"""
Y UNIVERSE AWARDS 2025 Deep Dive Dashboard (dashboard_two.py)
วิเคราะห์เจาะลึก: คำนวนคะแนนจริงและยอดเงิน (Monotonic Vote Reconstruction)
รันที่ Port: 5001
"""

from flask import Flask, render_template_string, jsonify
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

app = Flask(__name__)
DATA_DIR = Path('data_yna2025')

# Constants
VOTE_COST = 4.0  # 4 Baht per vote (1000 votes = 4000 THB)
BASE_TOTAL_VOTES = 100000  # Initial assumption of total votes in the system

def load_data():
    """Load all JSON files and return as a DataFrame"""
    records = []
    files = sorted(DATA_DIR.glob('vote_*.json'))
    
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                timestamp = data.get('timestamp')
                # If timestamp is missing or invalid, try to parse from filename
                if not timestamp:
                    ts_str = f.stem.replace('vote_', '')
                    try:
                        timestamp = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").isoformat()
                    except:
                        continue

                # Parse summary
                summary = data.get('summary', [])
                row = {'timestamp': timestamp}
                for item in summary:
                    code = item['code']
                    row[f'{code}_pct'] = item['percentage']
                    row[f'{code}_name'] = item['names']
                    row[f'{code}_series'] = item['series']
                records.append(row)
        except Exception as e:
            print(f"Error loading {f}: {e}")
            continue
            
    if not records:
        return pd.DataFrame()
        
    df = pd.DataFrame(records)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    return df

def reconstruct_votes(df):
    """
    Cumulative Gain Only Algorithm
    
    Logic:
    - Track each candidate's percentage over time.
    - When a candidate's % INCREASES, calculate the gain and convert to votes.
    - Votes ADDED = (pct_gain) * (BASE_TOTAL_VOTES / 100)
    - When % DECREASES, ignore it (votes stay the same, no loss).
    - Total votes = Sum of all individual candidate votes.
    """
    if df.empty:
        return {}, []

    # Identify candidate columns
    pct_cols = [c for c in df.columns if c.endswith('_pct')]
    candidates = [c.replace('_pct', '') for c in pct_cols]
    
    # Initialize: Track cumulative votes and previous percentages
    cumulative_votes = {c: 0.0 for c in candidates}
    prev_pct = {c: 0.0 for c in candidates}
    
    history = []
    
    for _, row in df.iterrows():
        step_data = {
            'timestamp': row['timestamp'],
        }
        
        for c in candidates:
            pct = row.get(f'{c}_pct', 0)
            
            # Calculate gain (only if positive)
            pct_change = pct - prev_pct[c]
            
            if pct_change > 0:
                # Convert % gain to votes: 1% = 1000 votes (since BASE = 100,000)
                votes_added = (pct_change / 100.0) * BASE_TOTAL_VOTES
                cumulative_votes[c] += votes_added
            
            # Update previous percentage for next iteration
            prev_pct[c] = pct
            
            step_data[f'{c}_votes'] = cumulative_votes[c]
            step_data[f'{c}_cost'] = cumulative_votes[c] * VOTE_COST
            step_data[f'{c}_name'] = row.get(f'{c}_name', '')
            step_data[f'{c}_pct'] = pct
        
        # Calculate total votes as sum of all candidates
        step_data['total_votes'] = sum(cumulative_votes.values())
            
        history.append(step_data)
        
    return history, candidates

@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    df = load_data()
    history, candidates = reconstruct_votes(df)
    
    if not history:
        return jsonify({'error': 'No data'})
        
    # Format for frontend
    latest = history[-1]
    
    # Summary List (Sorted by Votes)
    summary = []
    for c in candidates:
        summary.append({
            'code': c,
            'name': latest.get(f'{c}_name', ''),
            'votes': round(latest.get(f'{c}_votes', 0)),
            'cost': round(latest.get(f'{c}_cost', 0)),
            'pct': latest.get(f'{c}_pct', 0)
        })
    summary.sort(key=lambda x: x['votes'], reverse=True)
    
    # Time Series for Graph (simplified)
    # We'll send data for YND06, YND10, and maybe others if needed
    labels = [h['timestamp'].strftime('%d/%H:%M') for h in history]
    
    series = {}
    for c in candidates:
        series[c] = [round(h.get(f'{c}_votes', 0)) for h in history]
    
    # Process ALL History (No Skipping)
    full_records = []
    
    # Iterate through history to format and calculate deltas
    for i, h in enumerate(history):
        current = h
        prev = history[i-1] if i > 0 else None
        
        ts_obj = current['timestamp'] if isinstance(current['timestamp'], datetime) else pd.to_datetime(current['timestamp'])
        time_str = ts_obj.strftime('%Y-%m-%d %H:%M:%S')
        
        rec = {
            'time': time_str,
            'total_votes': round(current.get('total_votes', 0)),
            'total_change': round(current.get('total_votes', 0) - (prev.get('total_votes', 0) if prev else 0)),
            'candidates': {}
        }
        
        for c in candidates:
            cur_votes = round(current.get(f'{c}_votes', 0))
            cur_cost = round(current.get(f'{c}_cost', 0))
            cur_pct = current.get(f'{c}_pct', 0)
            
            if prev:
                prev_votes = round(prev.get(f'{c}_votes', 0))
                prev_cost = round(prev.get(f'{c}_cost', 0))
                prev_pct = prev.get(f'{c}_pct', 0)
                
                diff_votes = cur_votes - prev_votes
                diff_cost = cur_cost - prev_cost
                diff_pct = cur_pct - prev_pct
            else:
                diff_votes = 0
                diff_cost = 0
                diff_pct = 0
            
            rec['candidates'][c] = {
                'votes': cur_votes,
                'cost': cur_cost,
                'pct': cur_pct,
                'diff_votes': diff_votes,
                'diff_cost': diff_cost,
                'diff_pct': diff_pct
            }
        full_records.append(rec)

    # Group by Date
    grouped_history = {}
    for rec in full_records:
        date_key = rec['time'].split(' ')[0] # YYYY-MM-DD
        if date_key not in grouped_history:
            grouped_history[date_key] = []
        grouped_history[date_key].append(rec)
    
    # Convert to list of {date: ..., records: [...]}
    final_hourly = []
    for date in sorted(grouped_history.keys(), reverse=True):
         # Sort records to be ASCENDING (Time Low -> Time High)
         records_asc = sorted(grouped_history[date], key=lambda x: x['time'])
         final_hourly.append({
             'date': date,
             'records': records_asc
         })
         
    # Calculate Projection Model
    # Deadline: Jan 9, 2026 12:00
    deadline = datetime(2026, 1, 9, 12, 0, 0)
    now = datetime.now()
    hours_remaining = max(0, (deadline - now).total_seconds() / 3600)
    
    # Calculate hourly growth rate (last 6 hours average)
    projection = {'ynd06': {}, 'ynd10': {}, 'hours_remaining': round(hours_remaining, 1)}
    
    if len(history) >= 2:
        # Get data points from last 6 hours
        recent_hours = 6
        recent_data = [h for h in history if (now - pd.to_datetime(h['timestamp'])).total_seconds() < recent_hours * 3600]
        
        if len(recent_data) >= 2:
            # First and last data points in recent window
            first = recent_data[0]
            last = recent_data[-1]
            
            time_diff_hours = (pd.to_datetime(last['timestamp']) - pd.to_datetime(first['timestamp'])).total_seconds() / 3600
            
            if time_diff_hours > 0:
                # YND06 growth rate
                ynd06_start = first.get('YND06_votes', 0)
                ynd06_end = last.get('YND06_votes', 0)
                ynd06_rate = (ynd06_end - ynd06_start) / time_diff_hours
                
                # YND10 growth rate
                ynd10_start = first.get('YND10_votes', 0)
                ynd10_end = last.get('YND10_votes', 0)
                ynd10_rate = (ynd10_end - ynd10_start) / time_diff_hours
                
                # Current votes
                ynd06_current = latest.get('YND06_votes', 0)
                ynd10_current = latest.get('YND10_votes', 0)
                
                # Projections at deadline (normal rate)
                ynd06_projected_normal = ynd06_current + (ynd06_rate * hours_remaining)
                ynd10_projected_normal = ynd10_current + (ynd10_rate * hours_remaining)
                
                # Projections with surge (100x rate for last 3 hours)
                surge_hours = min(3, hours_remaining)
                normal_hours = hours_remaining - surge_hours
                
                ynd06_projected_surge = ynd06_current + (ynd06_rate * normal_hours) + (ynd06_rate * 100 * surge_hours)
                ynd10_projected_surge = ynd10_current + (ynd10_rate * normal_hours) + (ynd10_rate * 100 * surge_hours)
                
                projection['ynd06'] = {
                    'current': round(ynd06_current),
                    'rate_per_hour': round(ynd06_rate),
                    'projected_normal': round(ynd06_projected_normal),
                    'projected_surge': round(ynd06_projected_surge)
                }
                
                projection['ynd10'] = {
                    'current': round(ynd10_current),
                    'rate_per_hour': round(ynd10_rate),
                    'projected_normal': round(ynd10_projected_normal),
                    'projected_surge': round(ynd10_projected_surge)
                }
                
                # Winner predictions
                projection['winner_normal'] = 'YND06' if ynd06_projected_normal > ynd10_projected_normal else 'YND10'
                projection['winner_surge'] = 'YND06' if ynd06_projected_surge > ynd10_projected_surge else 'YND10'
                projection['gap_normal'] = round(abs(ynd06_projected_normal - ynd10_projected_normal))
                projection['gap_surge'] = round(abs(ynd06_projected_surge - ynd10_projected_surge))
         
    return jsonify({
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': summary,
        'history': {
            'labels': labels,
            'series': series
        },
        'hourly_grouped': final_hourly,
        'total_votes': round(latest.get('total_votes', 0)),
        'total_money': round(latest.get('total_votes', 0) * VOTE_COST),
        'projection': projection
    })

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deep Dive: Y UNIVERSE Vote Analysis</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Kanit', sans-serif; background-color: #0f172a; color: #e2e8f0; }
        .card { background-color: #1e293b; border-radius: 1rem; padding: 1.5rem; border: 1px solid #334155; }
        .text-neon { color: #38bdf8; text-shadow: 0 0 10px rgba(56, 189, 248, 0.5); }
        .text-gold { color: #fbbf24; text-shadow: 0 0 10px rgba(251, 191, 36, 0.3); }
        .text-danger { color: #f87171; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }
        th { font-weight: 600; color: #94a3b8; }
        tr:hover { background-color: rgba(51, 65, 85, 0.5); }
        .diff-pos { color: #4ade80; font-size: 0.75em; }
        .diff-neg { color: #f87171; font-size: 0.75em; }
        .diff-neu { color: #94a3b8; font-size: 0.75em; }
        .date-header { background-color: #334155; color: #fbbf24; font-weight: bold; padding: 10px; border-radius: 5px; margin-top: 15px; margin-bottom: 5px; }
    </style>
</head>
<body class="p-6">
    <div class="max-w-7xl mx-auto">
        <header class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">
                    🚀 Y UNIVERSE Analyze System
                </h1>
                <p class="text-slate-400 text-sm mt-1">Estimating utilizing Monotonic Growth Algorithm (Base Cost: 4 THB/Vote)</p>
            </div>
            <div class="text-right">
                <div id="last-update" class="text-sm text-slate-500">Loading...</div>
                <div class="flex gap-2 mt-2">
                    <span class="px-3 py-1 bg-blue-900/30 text-blue-400 rounded-full text-xs border border-blue-800">Live Auto-Update</span>
                </div>
            </div>
        </header>

        <!-- Top Stats -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div class="card bg-gradient-to-br from-indigo-900/50 to-slate-900">
                <div class="text-slate-400 text-sm">Estimated Total Votes</div>
                <div class="text-3xl font-bold text-white mt-1" id="total-votes">-</div>
            </div>
            <div class="card bg-gradient-to-br from-emerald-900/50 to-slate-900">
                <div class="text-slate-400 text-sm">Estimated Total Money</div>
                <div class="text-3xl font-bold text-emerald-400 mt-1" id="total-money">-</div>
            </div>
             <div class="card md:col-span-2">
                <div class="text-slate-400 text-sm mb-2">Algorithm Note</div>
                <div class="text-xs text-slate-500">
                    สูตร Cumulative Gain Only: นับเฉพาะ % ที่เพิ่มขึ้นเป็นคะแนนสะสม
                    <br>ราคาประเมิน: 1 Vote = 4 THB (เรท 1000 คะแนน).
                </div>
            </div>
        </div>
        
        <!-- YND06 Victory Prediction -->
        <div class="card bg-gradient-to-br from-blue-900/40 via-slate-900 to-yellow-900/30 mb-8 border-2 border-blue-500/30">
            <div class="flex items-center gap-2 mb-4">
                <span class="text-2xl">🎯</span>
                <h2 class="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-yellow-400">
                    YND06 ต้องโหวตอีกเท่าไหร่จะชนะ YND10?
                </h2>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <!-- Gap -->
                <div class="bg-slate-800/50 rounded-lg p-4 text-center">
                    <div class="text-slate-400 text-sm mb-1">ห่างอยู่</div>
                    <div class="text-3xl font-bold text-red-400" id="pred-gap">-</div>
                    <div class="text-xs text-slate-500">คะแนน</div>
                </div>
                
                <!-- Votes Needed -->
                <div class="bg-slate-800/50 rounded-lg p-4 text-center">
                    <div class="text-slate-400 text-sm mb-1">YND06 ต้องเพิ่มอีก</div>
                    <div class="text-3xl font-bold text-blue-400" id="pred-votes">-</div>
                    <div class="text-xs text-slate-500">คะแนน (เพื่อชนะ)</div>
                </div>
                
                <!-- Cost Needed -->
                <div class="bg-slate-800/50 rounded-lg p-4 text-center">
                    <div class="text-slate-400 text-sm mb-1">ต้องใช้เงินอีก</div>
                    <div class="text-3xl font-bold text-emerald-400" id="pred-cost">-</div>
                    <div class="text-xs text-slate-500">บาท</div>
                </div>
            </div>
            
            <!-- Countdown -->
            <div class="bg-slate-800/50 rounded-lg p-4">
                <div class="flex justify-between items-center">
                    <div>
                        <div class="text-slate-400 text-sm">⏰ เหลือเวลาโหวต</div>
                        <div class="text-2xl font-bold text-yellow-400" id="pred-countdown">--:--:--</div>
                    </div>
                    <div class="text-right">
                        <div class="text-slate-500 text-sm">หมดเขต</div>
                        <div class="text-lg text-slate-300">9 ม.ค. 2569 เวลา 12:00 น.</div>
                    </div>
                </div>
            </div>
            
            <!-- Projection Model -->
            <div class="mt-4 bg-gradient-to-r from-purple-900/30 to-indigo-900/30 rounded-lg p-4 border border-purple-500/30">
                <div class="flex items-center gap-2 mb-3">
                    <span class="text-xl">🔮</span>
                    <h3 class="font-bold text-purple-300">คาดการณ์ ณ เวลาปิดโหวต</h3>
                    <span class="text-xs text-slate-500">(คำนวนจากอัตราโหวต 6 ชม.ล่าสุด)</span>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <!-- Normal Scenario -->
                    <div class="bg-slate-900/50 rounded-lg p-4">
                        <div class="text-sm text-slate-400 mb-3">📈 Scenario 1: อัตราปกติ</div>
                        
                        <div class="mb-3">
                            <div class="text-xs text-yellow-400 mb-1">YND10 จะปิดที่ประมาณ:</div>
                            <div class="text-2xl font-bold font-mono text-yellow-200" id="proj-ynd10-closing-normal">-</div>
                        </div>
                        
                        <div class="bg-blue-900/30 rounded-lg p-3 border border-blue-500/30">
                            <div class="text-xs text-blue-400 mb-1">YND06 ต้องโหวตเพิ่มอีก (เพื่อชนะ):</div>
                            <div class="text-2xl font-bold font-mono text-blue-300" id="proj-ynd06-needed-normal">-</div>
                            <div class="text-xs text-emerald-400 mt-1" id="proj-ynd06-cost-normal">-</div>
                        </div>
                    </div>
                    
                    <!-- Surge Scenario -->
                    <div class="bg-slate-900/50 rounded-lg p-4">
                        <div class="text-sm text-slate-400 mb-3">
                            🚀 Scenario 2: สปริ้นท์ 3 ชม.สุดท้าย 
                            <input type="number" id="surge-multiplier" value="100" min="1" max="1000" 
                                   class="w-20 ml-2 px-2 py-1 rounded bg-slate-800 border border-purple-500/50 text-center text-purple-300 font-bold"
                                   onchange="recalculateSurge()">
                            <span class="text-purple-400">x</span>
                        </div>
                        
                        <div class="mb-3">
                            <div class="text-xs text-yellow-400 mb-1">YND10 จะปิดที่ประมาณ:</div>
                            <div class="text-2xl font-bold font-mono text-yellow-200" id="proj-ynd10-closing-surge">-</div>
                        </div>
                        
                        <div class="bg-blue-900/30 rounded-lg p-3 border border-blue-500/30">
                            <div class="text-xs text-blue-400 mb-1">YND06 ต้องโหวตเพิ่มอีก (เพื่อชนะ):</div>
                            <div class="text-2xl font-bold font-mono text-blue-300" id="proj-ynd06-needed-surge">-</div>
                            <div class="text-xs text-emerald-400 mt-1" id="proj-ynd06-cost-surge">-</div>
                        </div>
                    </div>
                </div>
                
                <!-- Growth Rate Info -->
                <div class="mt-3 text-xs text-slate-500 flex flex-wrap gap-4">
                    <span>📊 YND06 อัตราปัจจุบัน: <span id="proj-rate-ynd06" class="text-blue-400">-</span> votes/hr</span>
                    <span>📊 YND10 อัตราปัจจุบัน: <span id="proj-rate-ynd10" class="text-yellow-400">-</span> votes/hr</span>
                </div>
            </div>
            
            <!-- Status Message -->
            <div class="mt-4 text-center" id="pred-status">
                <!-- Dynamic status message -->
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <!-- Left: Leaderboard -->
            <div class="lg:col-span-1 space-y-6">
                <!-- Leaderboard Card -->
                <div class="card">
                     <h2 class="text-xl font-bold text-gold mb-4">🏆 Current Standings</h2>
                    <div id="leaderboard" class="space-y-3">
                        <!-- Items injected here -->
                    </div>
                </div>
            </div>

            <!-- Right: Comparisons -->
            <div class="lg:col-span-2 space-y-6">
                <!-- Head to Head -->
                <div class="card">
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-xl font-bold text-neon">⚔️ Head-to-Head: YND06 vs YND10</h2>
                        <div class="text-xs text-slate-400">Vote Growth Over Time</div>
                    </div>
                    <div class="h-[300px] w-full">
                        <canvas id="compChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Hourly History Table Full Width -->
        <div class="card mb-8">
            <h2 class="text-xl font-bold text-white mb-4">🕒 Hourly History (Estimates)</h2>
            <div id="hourlyContainerDesktop">
                <!-- Items Injected Here -->
            </div>
        </div>
    </div>

    <script>
        let compChartInstance = null;
        let allChartInstance = null;
        
        // Countdown Timer for Voting Deadline: Jan 9, 2026 12:00 (Bangkok Time)
        const VOTE_DEADLINE = new Date('2026-01-09T12:00:00+07:00');
        
        function updateCountdown() {
            const now = new Date();
            const diff = VOTE_DEADLINE - now;
            
            if (diff <= 0) {
                document.getElementById('pred-countdown').innerHTML = '<span class="text-red-500">หมดเวลาแล้ว!</span>';
                return;
            }
            
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);
            
            document.getElementById('pred-countdown').innerText = 
                `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
        
        // Start countdown
        setInterval(updateCountdown, 1000);
        updateCountdown();
        
        // Store projection data globally for recalculation
        let cachedProjection = null;
        
        function recalculateSurge() {
            if (!cachedProjection) return;
            
            const multiplier = parseInt(document.getElementById('surge-multiplier').value) || 100;
            const proj = cachedProjection;
            
            // Calculate surge with custom multiplier
            const hoursRemaining = proj.hours_remaining || 0;
            const surgeHours = Math.min(3, hoursRemaining);
            const normalHours = hoursRemaining - surgeHours;
            
            const ynd10Rate = proj.ynd10.rate_per_hour || 0;
            const ynd06Rate = proj.ynd06.rate_per_hour || 0;
            const ynd06Current = proj.ynd06.current || 0;
            const ynd10Current = proj.ynd10.current || 0;
            
            // Calculate YND10 closing with custom surge
            const ynd10ClosingSurge = ynd10Current + (ynd10Rate * normalHours) + (ynd10Rate * multiplier * surgeHours);
            const ynd06NeededSurge = Math.max(0, ynd10ClosingSurge - ynd06Current + 1);
            const ynd06CostSurge = ynd06NeededSurge * 4;
            
            document.getElementById('proj-ynd10-closing-surge').innerText = formatNumber(Math.round(ynd10ClosingSurge));
            document.getElementById('proj-ynd06-needed-surge').innerText = formatNumber(Math.round(ynd06NeededSurge)) + ' โหวต';
            document.getElementById('proj-ynd06-cost-surge').innerText = '≈ ' + formatMoney(Math.round(ynd06CostSurge));
        }

        async function fetchData() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                renderDashboard(data);
            } catch (e) {
                console.error("Fetch error", e);
            }
        }

        function formatMoney(n) {
            return new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB', maximumFractionDigits: 0 }).format(n);
        }
        
        function formatNumber(n) {
            return new Intl.NumberFormat('th-TH').format(n);
        }
        
        function formatDelta(n, prefix='') {
            if (n > 0) return `<span class="diff-pos">▲${formatNumber(n)}</span>`;
            if (n < 0) return `<span class="diff-neg">▼${formatNumber(n)}</span>`;
            return `<span class="diff-neu">-</span>`;
        }
        
        function formatMoneyDelta(n) {
            if (n > 0) return `<span class="diff-pos">+${formatNumber(n)}฿</span>`;
            if (n < 0) return `<span class="diff-neg">${formatNumber(n)}฿</span>`;
            return ``;
        }

        function renderDashboard(data) {
            document.getElementById('last-update').innerText = 'Last update: ' + data.timestamp;
            document.getElementById('total-votes').innerText = formatNumber(data.total_votes);
            document.getElementById('total-money').innerText = formatMoney(data.total_money);

            // Render Leaderboard
            const lb = document.getElementById('leaderboard');
            lb.innerHTML = '';
            // Filter to only YND10 and YND06
            const filteredSummary = data.summary.filter(item => item.code === 'YND10' || item.code === 'YND06');
            filteredSummary.forEach((item, index) => {
                const highlightClass = index === 0 ? 'border-yellow-500/50 bg-yellow-900/10' : 'border-blue-500/50 bg-blue-900/10';
                const rankColor = index === 0 ? 'text-yellow-400' : 'text-blue-400';
                
                lb.innerHTML += `
                    <div class="p-4 rounded-lg flex justify-between items-center ${highlightClass} border mb-3 transition hover:scale-[1.01]">
                        <div class="flex items-center gap-3">
                            <div class="text-2xl font-bold w-8 text-center ${rankColor}">#${index+1}</div>
                            <div>
                                <div class="font-bold text-lg text-white pb-0.5 mb-0.5">
                                    ${item.code} <span class="text-sm font-normal ${rankColor} ml-1">${item.pct}%</span>
                                </div>
                                <div class="text-xs text-slate-400 truncate max-w-[180px]">${item.name}</div>
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-xl font-bold text-neon">${formatNumber(item.votes)}</div>
                            <div class="text-sm text-emerald-400">${formatMoney(item.cost)}</div>
                        </div>
                    </div>
                `;
            });
            
            // Render Prediction (YND06 vs YND10)
            const ynd06Data = data.summary.find(s => s.code === 'YND06');
            const ynd10Data = data.summary.find(s => s.code === 'YND10');
            
            if (ynd06Data && ynd10Data) {
                const gap = ynd10Data.votes - ynd06Data.votes;
                const votesNeeded = gap + 1; // +1 to win
                const costNeeded = votesNeeded * 4;
                
                document.getElementById('pred-gap').innerText = formatNumber(Math.abs(gap));
                document.getElementById('pred-votes').innerText = formatNumber(votesNeeded > 0 ? votesNeeded : 0);
                document.getElementById('pred-cost').innerText = formatMoney(costNeeded > 0 ? costNeeded : 0);
            }
            
            // Render Projection Model
            if (data.projection && data.projection.ynd06 && data.projection.ynd10) {
                const proj = data.projection;
                cachedProjection = proj; // Store for recalculateSurge
                const ynd06Current = proj.ynd06.current || 0;
                
                // Normal scenario
                const ynd10ClosingNormal = proj.ynd10.projected_normal || 0;
                const ynd06NeededNormal = Math.max(0, ynd10ClosingNormal - ynd06Current + 1); // +1 to win
                const ynd06CostNormal = ynd06NeededNormal * 4;
                
                document.getElementById('proj-ynd10-closing-normal').innerText = formatNumber(ynd10ClosingNormal);
                document.getElementById('proj-ynd06-needed-normal').innerText = formatNumber(ynd06NeededNormal) + ' โหวต';
                document.getElementById('proj-ynd06-cost-normal').innerText = '≈ ' + formatMoney(ynd06CostNormal);
                
                // Surge scenario - use recalculateSurge for dynamic multiplier
                recalculateSurge();
                
                // Growth rates
                document.getElementById('proj-rate-ynd06').innerText = formatNumber(proj.ynd06.rate_per_hour || 0);
                document.getElementById('proj-rate-ynd10').innerText = formatNumber(proj.ynd10.rate_per_hour || 0);
                
                // Status message based on normal projection only
                const statusEl = document.getElementById('pred-status');
                if (ynd06NeededNormal <= 0) {
                    statusEl.innerHTML = `<span class="text-2xl">🎉</span> <span class="text-xl font-bold text-blue-400">YND06 กำลังนำอยู่!</span>`;
                } else if (ynd06NeededNormal > 5000) {
                    statusEl.innerHTML = `<span class="text-2xl">⚠️</span> <span class="text-xl font-bold text-yellow-400">ต้องเร่งโหวต YND06 มากขึ้น!</span>`;
                } else {
                    statusEl.innerHTML = `<span class="text-2xl">🔥</span> <span class="text-xl font-bold text-orange-400">สูสี! เร่งโหวต YND06 ก่อนหมดเวลา!</span>`;
                }
            }
            
            // Render Hourly Table (Desktop + Grouped) - TRANSPOSED LAYOUT (Time as Columns)
            const dtContainer = document.getElementById('hourlyContainerDesktop');
            dtContainer.innerHTML = '';
            
            // Get all candidate codes from the first available record
            // Only show YND10 and YND06
            const allCodes = ['YND10', 'YND06'];

            data.hourly_grouped.forEach(group => {
                // Header
                dtContainer.innerHTML += `<div class="date-header">📅 ${group.date}</div>`;
                
                // We need to pivot.
                // Columns: [Label] [Time 1] [Time 2] ...
                // Rows: [YND10], [YND06]
                
                const times = [...group.records].reverse(); // Reverse: Latest first -> Oldest last
                
                // Build Table Header (Verify Times)
                let headerHtml = `
                    <thead>
                        <tr>
                            <th class="sticky left-0 bg-slate-800 z-10 w-24 border-r border-slate-700">Candidate</th>
                `;
                times.forEach(rec => {
                    headerHtml += `<th class="min-w-[100px] text-slate-400 font-mono text-xs">${rec.time.split(' ')[1]}</th>`;
                });
                headerHtml += `</tr></thead>`;

                // Build Table Body
                let bodyHtml = `<tbody>`;
                allCodes.forEach(code => {
                     const isMain = (code === 'YND10' || code === 'YND06');
                     const nameColor = isMain ? (code === 'YND10' ? 'text-yellow-400' : 'text-blue-400') : 'text-slate-400';
                     const voteColor = isMain ? (code === 'YND10' ? 'text-yellow-200' : 'text-blue-200') : 'text-slate-400';
                     
                     bodyHtml += `
                        <tr class="border-b border-slate-700/50 hover:bg-slate-800/50">
                            <td class="sticky left-0 bg-slate-900/90 font-bold ${nameColor} border-r border-slate-700 p-3">${code}</td>
                     `;
                     
                     times.forEach(rec => {
                         const cand = rec.candidates[code];
                         if (!cand) {
                             bodyHtml += `<td>-</td>`;
                             return;
                         }
                         
                         bodyHtml += `
                            <td>
                                <div class="font-mono ${voteColor}">${formatNumber(cand.votes)}</div>
                                <div class="flex items-center gap-1 text-[10px]">
                                    <span class="text-slate-500">${cand.pct.toFixed(2)}%</span>
                                    ${formatDelta(cand.diff_votes)}
                                </div>
                                <div class="text-[10px] opacity-60">${formatMoneyDelta(cand.diff_cost)}</div>
                            </td>
                         `;
                     });
                     
                     bodyHtml += `</tr>`;
                });
                
                bodyHtml += `</tbody>`;
                
                dtContainer.innerHTML += `
                    <div class="overflow-x-auto mb-4 border border-slate-700 rounded-lg">
                        <table class="w-full text-sm whitespace-nowrap">
                            ${headerHtml}
                            ${bodyHtml}
                        </table>
                    </div>
                `;
            });
            
            // Ensure mobile visibility (using same view)
            try {
                const mobileCard = document.querySelector('.card.lg\\:hidden');
                const desktopCard = document.querySelector('.card.hidden.lg\\:block');
                if (mobileCard) mobileCard.style.display = 'none';
                if (desktopCard) desktopCard.classList.remove('hidden', 'lg:block');
            } catch(e) {
                console.warn('Could not toggle mobile/desktop views:', e);
            }

            
            // Render Head-to-Head Chart (YND06 vs YND10)
            const ctxComp = document.getElementById('compChart').getContext('2d');
            const ynd06 = data.history.series['YND06'];
            const ynd10 = data.history.series['YND10'];
            
            if (compChartInstance) compChartInstance.destroy();
            compChartInstance = new Chart(ctxComp, {
                type: 'line',
                data: {
                    labels: data.history.labels,
                    datasets: [
                        {
                            label: 'YND06',
                            data: ynd06,
                            borderColor: '#38bdf8', // Neon Blue
                            backgroundColor: 'rgba(56, 189, 248, 0.1)',
                            borderWidth: 3,
                            fill: true,
                            tension: 0.4
                        },
                        {
                            label: 'YND10',
                            data: ynd10,
                            borderColor: '#fbbf24', // Gold
                            backgroundColor: 'rgba(251, 191, 36, 0.1)',
                            borderWidth: 3,
                            fill: true,
                            tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { color: '#cbd5e1' } } },
                    scales: {
                        y: { 
                            grid: { color: '#334155' },
                            ticks: { color: '#94a3b8' }
                        },
                        x: { 
                            grid: { display: false },
                            ticks: { color: '#94a3b8', maxTicksLimit: 10 }
                        }
                    }
                }
            });

            // Render All Chart
            const ctxAll = document.getElementById('allChart').getContext('2d');
            const datasets = [];
            const colors = ['#f472b6', '#a78bfa', '#34d399', '#fca5a5', '#9ca3af'];
            
            let colorIdx = 0;
            data.summary.forEach((item) => {
                 if (item.code === 'YND06' || item.code === 'YND10') return; // Skip main duo (already in top chart, or add if you want all)
                 
                 // Add top 5 others
                 if (item.votes > 100) {
                     datasets.push({
                        label: item.code,
                        data: data.history.series[item.code],
                        borderColor: colors[colorIdx % colors.length],
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                     });
                     colorIdx++;
                 }
            });
            
            // Add main duo back but thinner for context? Or just keep separate. 
            // Let's add them back as reference but dashed lines
             datasets.push({
                label: 'YND06',
                data: ynd06,
                borderColor: '#38bdf8',
                borderWidth: 1,
                borderDash: [5, 5],
                pointRadius: 0
            });
             datasets.push({
                label: 'YND10',
                data: ynd10,
                borderColor: '#fbbf24',
                borderWidth: 1,
                borderDash: [5, 5],
                pointRadius: 0
            });

            if (allChartInstance) allChartInstance.destroy();
            allChartInstance = new Chart(ctxAll, {
                type: 'line',
                data: {
                    labels: data.history.labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'right', labels: { color: '#cbd5e1', boxWidth: 12 } } },
                    scales: {
                        y: { 
                            grid: { color: '#334155' },
                            ticks: { color: '#94a3b8' }
                        },
                        x: { 
                            display: false 
                        }
                    }
                }
            });
        }

        // Auto Refresh
        fetchData();
        setInterval(fetchData, 60000); // 1 minute
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("🚀 Starting Dashboard Two on port 5001...")
    # Run slightly different port to avoid conflict
    app.run(debug=True, host='0.0.0.0', port=5001)
