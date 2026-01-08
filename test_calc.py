"""
Test script to compare vote calculation between dashboard.py and dashboard_two.py
"""
from pathlib import Path
import json
from datetime import datetime
import pandas as pd

DATA_DIR = Path('data_yna2025')
BASE_TOTAL_VOTES = 100000

# Method 1: dashboard_two.py style (pandas)
def calc_dashboard_two():
    records = []
    for f in sorted(DATA_DIR.glob("vote_*.json")):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            timestamp = data.get('timestamp')
            if not timestamp:
                ts_str = f.stem.replace('vote_', '')
                try:
                    timestamp = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").isoformat()
                except:
                    continue
            summary = data.get('summary', [])
            row = {'timestamp': timestamp}
            for item in summary:
                code = item['code']
                row[f'{code}_pct'] = item['percentage']
            records.append(row)
        except Exception as e:
            continue
    
    if not records:
        return {}
    
    df = pd.DataFrame(records)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    pct_cols = [c for c in df.columns if c.endswith('_pct')]
    candidates = [c.replace('_pct', '') for c in pct_cols]
    
    cumulative_votes = {c: 0.0 for c in candidates}
    prev_pct = {c: 0.0 for c in candidates}
    
    for _, row in df.iterrows():
        for c in candidates:
            pct = row.get(f'{c}_pct', 0)
            if pd.isna(pct):
                pct = 0
            pct_change = pct - prev_pct[c]
            if pct_change > 0:
                votes_added = (pct_change / 100.0) * BASE_TOTAL_VOTES
                cumulative_votes[c] += votes_added
            prev_pct[c] = pct
    
    return cumulative_votes


# Method 2: dashboard.py style (plain Python)
def calc_dashboard():
    json_files = sorted(DATA_DIR.glob('vote_*.json'))
    
    all_codes = set()
    history_data = []
    
    for file in json_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            timestamp = data.get('timestamp', '')
            raw_timestamp = timestamp
            
            vote_data = {}
            if 'summary' in data:
                for item in data['summary']:
                    code = item.get('code', '')
                    pct = item.get('percentage', 0)
                    vote_data[code] = pct
                    all_codes.add(code)
            
            history_data.append({
                'raw_timestamp': raw_timestamp,
                'data': vote_data
            })
        except:
            continue
    
    history_data.sort(key=lambda x: x['raw_timestamp'])
    
    codes = sorted(list(all_codes))
    cumulative_points = {code: 0.0 for code in codes}
    prev_pct = {code: 0.0 for code in codes}
    
    for entry in history_data:
        current_pct = entry['data']
        for code in codes:
            curr = current_pct.get(code, 0)
            prev = prev_pct.get(code, 0)
            if curr > prev:
                delta = curr - prev
                points_added = (delta / 100) * BASE_TOTAL_VOTES
                cumulative_points[code] += points_added
            prev_pct[code] = curr
    
    return cumulative_points


if __name__ == "__main__":
    print("="*50)
    print("Dashboard Two (pandas method):")
    result1 = calc_dashboard_two()
    print(f"  YND06: {round(result1.get('YND06', 0))}")
    print(f"  YND10: {round(result1.get('YND10', 0))}")
    
    print()
    print("Dashboard (plain Python method):")
    result2 = calc_dashboard()
    print(f"  YND06: {round(result2.get('YND06', 0))}")
    print(f"  YND10: {round(result2.get('YND10', 0))}")
    
    print()
    print("Difference:")
    print(f"  YND06: {round(result1.get('YND06', 0)) - round(result2.get('YND06', 0))}")
    print(f"  YND10: {round(result1.get('YND10', 0)) - round(result2.get('YND10', 0))}")
