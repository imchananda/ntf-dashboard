"""
Y UNIVERSE AWARDS 2025 Vote Dashboard
แสดงผลโหวตแบบ real-time + ดึงข้อมูลอัตโนมัติ
"""

from flask import Flask, render_template_string, jsonify, request
import json
from pathlib import Path
from datetime import datetime
import os
import requests
from bs4 import BeautifulSoup
import re
import threading
import time

app = Flask(__name__)

# โฟลเดอร์เก็บข้อมูล
DATA_DIR = Path('data_yna2025')
DATA_DIR.mkdir(exist_ok=True)

# ========== SCRAPER ==========

class VoteScraper:
    """Scraper สำหรับดึงผลโหวต"""
    
    def __init__(self):
        self.session = requests.Session()
        self.is_logged_in = False
        self.login_url = 'https://acmonlinebiz.com/yna2025/login_action.php'
        self.login_page = 'https://acmonlinebiz.com/yna2025/login.php'
        self.data_url = 'https://acmonlinebiz.com/yna2025/votesummary.php?tpid=4'
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'th,en;q=0.9',
        })
    
    def get_credentials(self):
        """ดึง credentials จาก environment variables"""
        username = os.environ.get('VOTE_USERNAME', '')
        password = os.environ.get('VOTE_PASSWORD', '')
        return username, password
    
    def login(self) -> bool:
        username, password = self.get_credentials()
        
        if not username or not password:
            print(f"⚠️ ไม่มี credentials - VOTE_USERNAME={bool(username)}, VOTE_PASSWORD={bool(password)}")
            return False
            
        try:
            print(f"🔐 กำลัง login ด้วย user: {username[:3]}***")
            self.session.get(self.login_page, timeout=30)
            
            payload = {
                'username': username,
                'userpassword': password,
            }
            
            response = self.session.post(self.login_url, data=payload, timeout=30, allow_redirects=True)
            
            if 'login' not in response.url.lower() or self.session.cookies.get_dict():
                self.is_logged_in = True
                print("✅ Login สำเร็จ")
                return True
                
            print("❌ Login ไม่สำเร็จ - ตรวจสอบ username/password")
            return False
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def fetch_vote_data(self) -> dict | None:
        if not self.is_logged_in:
            if not self.login():
                return None
        
        try:
            response = self.session.get(self.data_url, timeout=30)
            
            if 'login' in response.url.lower():
                self.is_logged_in = False
                if not self.login():
                    return None
                response = self.session.get(self.data_url, timeout=30)
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            vote_data = self._extract_chart_data(html)
            couples = self._extract_couple_names(soup)
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'url': self.data_url,
                'category': 'The Best Couple',
                'votes': vote_data,
                'couples': couples,
            }
            
            if vote_data and couples:
                result['summary'] = []
                labels = vote_data.get('labels', [])
                percentages = vote_data.get('data', [])
                
                for i, label in enumerate(labels):
                    couple_info = couples.get(label, {})
                    result['summary'].append({
                        'code': label,
                        'percentage': percentages[i] if i < len(percentages) else 0,
                        'names': couple_info.get('names', ''),
                        'series': couple_info.get('series', ''),
                    })
                
                result['summary'].sort(key=lambda x: x['percentage'], reverse=True)
            
            print(f"✅ ดึงข้อมูลสำเร็จ - {datetime.now().strftime('%H:%M:%S')}")
            return result
            
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            return None
    
    def _extract_chart_data(self, html: str) -> dict:
        result = {'labels': [], 'data': []}
        
        soup = BeautifulSoup(html, 'html.parser')
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string and 'Chart' in script.string:
                script_text = script.string
                
                labels_match = re.search(r'labels\s*:\s*\[(.*?)\]', script_text, re.DOTALL)
                if labels_match:
                    labels_str = labels_match.group(1)
                    result['labels'] = re.findall(r'["\']([^"\']+)["\']', labels_str)
                
                data_match = re.search(r"data\s*:\s*\[(.*?)\]", script_text, re.DOTALL)
                if data_match:
                    data_str = data_match.group(1)
                    numbers = re.findall(r'["\']?([\d.]+)["\']?', data_str)
                    result['data'] = [float(x) for x in numbers if x]
                
                if result['labels'] and result['data']:
                    break
        
        return result
    
    def _extract_couple_names(self, soup: BeautifulSoup) -> dict:
        couples = {}
        
        text = soup.get_text()
        for match in re.finditer(r'(YND\d+)\s*:\s*([^\n]+)', text):
            code = match.group(1)
            rest = match.group(2).strip()
            series_match = re.search(r'\(([^)]+)\)\s*$', rest)
            if series_match:
                series = series_match.group(1)
                names = rest[:series_match.start()].strip()
            else:
                series = ''
                names = rest
            
            couples[code] = {'names': names, 'series': series}
        
        return couples
    
    def save_data(self, data: dict) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = DATA_DIR / f"vote_{timestamp}.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 บันทึก: {json_file.name}")
        return str(json_file)
    
    def run_once(self) -> bool:
        data = self.fetch_vote_data()
        if data:
            self.save_data(data)
            return True
        return False


# Global scraper instance
scraper = VoteScraper()

def scraper_loop():
    """Background loop สำหรับดึงข้อมูลทุกชั่วโมง"""
    while True:
        try:
            print(f"\n🔄 กำลังดึงข้อมูล... {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            scraper.run_once()
        except Exception as e:
            print(f"❌ Scraper error: {e}")
        
        # รอ 1 ชั่วโมง
        time.sleep(3600)

# Start scraper thread
def start_scraper():
    username, password = scraper.get_credentials()
    if username and password:
        thread = threading.Thread(target=scraper_loop, daemon=True)
        thread.start()
        print("🚀 Scraper thread started")
    else:
        print(f"⚠️ ไม่มี credentials - Scraper ไม่ทำงาน (จะดึงเมื่อเรียก /api/scrape)")

# ========== END SCRAPER ==========

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Y UNIVERSE AWARDS 2025 Vote Dashboard - The Best Couple</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            padding: 30px 0;
            margin-bottom: 30px;
        }
        
        h1 {
            font-size: 2.5rem;
            background: linear-gradient(90deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        
        .subtitle {
            color: #a0a0a0;
            font-size: 1.1rem;
        }
        
        .update-time {
            color: #48dbfb;
            font-size: 0.95rem;
            margin-top: 10px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 15px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .stat-card.leader {
            background: linear-gradient(135deg, rgba(255, 215, 0, 0.2), rgba(255, 165, 0, 0.1));
            border-color: #ffd700;
        }
        
        .stat-card .rank {
            font-size: 0.85rem;
            color: #a0a0a0;
            margin-bottom: 5px;
        }
        
        .stat-card .code {
            font-size: 1.3rem;
            font-weight: bold;
            color: #48dbfb;
        }
        
        .stat-card.leader .code {
            color: #ffd700;
        }
        
        .stat-card .percentage {
            font-size: 2rem;
            font-weight: bold;
            margin: 8px 0;
        }
        
        .stat-card.leader .percentage {
            color: #ffd700;
        }
        
        .stat-card .names {
            font-size: 0.75rem;
            color: #ccc;
            line-height: 1.3;
        }
        
        .stat-card .series {
            font-size: 0.7rem;
            color: #888;
            margin-top: 5px;
        }
        
        .charts-section {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        
        @media (max-width: 900px) {
            .charts-section {
                grid-template-columns: 1fr;
            }
        }
        
        .chart-container {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .chart-container.full-width {
            grid-column: 1 / -1;
        }
        
        .chart-title {
            font-size: 1.2rem;
            margin-bottom: 20px;
            color: #48dbfb;
        }
        
        .table-container {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            overflow-x: auto;
            margin-bottom: 30px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 12px 8px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        th {
            background: rgba(72, 219, 251, 0.2);
            color: #48dbfb;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        
        tr:hover {
            background: rgba(255, 255, 255, 0.05);
        }
        
        .rank-badge {
            display: inline-block;
            width: 28px;
            height: 28px;
            line-height: 28px;
            text-align: center;
            border-radius: 50%;
            font-weight: bold;
            font-size: 0.85rem;
        }
        
        .rank-1 { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #000; }
        .rank-2 { background: linear-gradient(135deg, #c0c0c0, #a0a0a0); color: #000; }
        .rank-3 { background: linear-gradient(135deg, #cd7f32, #b87333); color: #fff; }
        .rank-other { background: rgba(255, 255, 255, 0.2); color: #fff; }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #48dbfb, #ff6b6b);
            border-radius: 4px;
            transition: width 0.5s ease;
        }
        
        .auto-refresh {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(72, 219, 251, 0.2);
            padding: 10px 20px;
            border-radius: 25px;
            font-size: 0.85rem;
            border: 1px solid #48dbfb;
        }
        
        .pulse {
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .loading {
            text-align: center;
            padding: 50px;
            color: #a0a0a0;
        }
        
        .section-title {
            font-size: 1.8rem;
            color: #feca57;
            margin: 40px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(254, 202, 87, 0.3);
        }
        
        .history-table th, .history-table td {
            padding: 8px 6px;
            font-size: 0.8rem;
            text-align: center;
        }
        
        .history-table th:first-child, .history-table td:first-child {
            text-align: left;
            position: sticky;
            left: 0;
            background: #1a1a2e;
            z-index: 1;
            min-width: 70px;
        }
        
        .change-up { color: #1dd1a1; }
        .change-down { color: #ff6b6b; }
        .change-same { color: #a0a0a0; }
        
        .summary-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .summary-card {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
        }
        
        .summary-card .label {
            color: #a0a0a0;
            font-size: 0.9rem;
            margin-bottom: 10px;
        }
        
        .summary-card .value {
            font-size: 1.8rem;
            font-weight: bold;
            color: #48dbfb;
        }
        
        /* Date Selector */
        .date-selector {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 20px;
            align-items: center;
        }
        
        .date-selector label {
            color: #a0a0a0;
            margin-right: 10px;
        }
        
        .date-btn {
            padding: 10px 20px;
            border: 2px solid #48dbfb;
            background: transparent;
            color: #48dbfb;
            border-radius: 25px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.3s;
        }
        
        .date-btn:hover {
            background: rgba(72, 219, 251, 0.2);
        }
        
        .date-btn.active {
            background: #48dbfb;
            color: #1a1a2e;
            font-weight: bold;
        }
        
        .tab-container {
            margin-bottom: 20px;
        }
        
        .tab-buttons {
            display: flex;
            gap: 5px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        
        .tab-btn {
            padding: 10px 25px;
            border: none;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border-radius: 10px 10px 0 0;
            cursor: pointer;
            font-size: 0.95rem;
            transition: all 0.3s;
        }
        
        .tab-btn:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        
        .tab-btn.active {
            background: rgba(72, 219, 251, 0.3);
            color: #48dbfb;
            font-weight: bold;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .money-highlight {
            color: #1dd1a1;
            font-weight: bold;
        }
        
        .votes-highlight {
            color: #feca57;
            font-weight: bold;
        }
        
        /* Calculator Section */
        .calculator-section {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .calc-input-container {
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        
        .calc-input-container label {
            font-size: 1rem;
            color: #48dbfb;
        }
        
        .calc-input-container input {
            padding: 10px 15px;
            font-size: 1rem;
            border: 2px solid #48dbfb;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            width: 180px;
        }
        
        .calc-input-container input:focus {
            outline: none;
            background: rgba(72, 219, 251, 0.2);
        }
        
        .calc-btn {
            padding: 10px 25px;
            font-size: 1rem;
            background: linear-gradient(135deg, #48dbfb, #0abde3);
            color: #1a1a2e;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-weight: bold;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .calc-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(72, 219, 251, 0.4);
        }
        
        .package-info {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        
        @media (max-width: 768px) {
            .package-info {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        
        .package-card {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 12px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .pkg-price {
            font-size: 1.2rem;
            font-weight: bold;
            color: #1dd1a1;
            margin-bottom: 3px;
        }
        
        .pkg-points {
            font-size: 0.95rem;
            color: #feca57;
            margin-bottom: 3px;
        }
        
        .pkg-rate {
            font-size: 0.75rem;
            color: #a0a0a0;
        }
        
        .calc-result {
            background: rgba(29, 209, 161, 0.1);
            border: 2px solid #1dd1a1;
            border-radius: 12px;
            padding: 20px;
            margin-top: 15px;
        }
        
        .result-title {
            font-size: 1.1rem;
            color: #1dd1a1;
            margin-bottom: 15px;
            font-weight: bold;
        }
        
        .result-content {
            margin-bottom: 15px;
        }
        
        .result-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            font-size: 0.9rem;
        }
        
        .result-item:last-child {
            border-bottom: none;
        }
        
        .result-item .pkg-name {
            color: #fff;
        }
        
        .result-item .pkg-qty {
            color: #48dbfb;
            font-weight: bold;
        }
        
        .result-item .pkg-subtotal {
            color: #1dd1a1;
        }
        
        .result-item .pkg-points-total {
            color: #feca57;
        }
        
        .result-summary {
            background: rgba(255, 215, 0, 0.1);
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        }
        
        .summary-row {
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
            font-size: 0.95rem;
        }
        
        .summary-total {
            font-size: 1.2rem;
            font-weight: bold;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 2px solid rgba(255, 215, 0, 0.3);
        }
        
        .summary-total .points {
            color: #ffd700;
        }
        
        .summary-total .money {
            color: #1dd1a1;
        }
        
        .summary-remaining {
            color: #ff6b6b;
            font-size: 0.85rem;
            margin-top: 8px;
        }
        
        /* Prediction Section */
        .prediction-section {
            background: linear-gradient(135deg, rgba(72, 130, 195, 0.2), rgba(30, 41, 59, 0.8), rgba(251, 191, 36, 0.15));
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 30px;
            border: 2px solid rgba(72, 130, 195, 0.3);
        }
        
        .pred-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .pred-icon {
            font-size: 1.8rem;
        }
        
        .pred-title {
            font-size: 1.4rem;
            font-weight: bold;
            background: linear-gradient(90deg, #48dbfb, #feca57);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .pred-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 15px;
        }
        
        @media (max-width: 768px) {
            .pred-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .pred-card {
            background: rgba(51, 65, 85, 0.5);
            border-radius: 12px;
            padding: 15px;
            text-align: center;
        }
        
        .pred-label {
            color: #94a3b8;
            font-size: 0.85rem;
            margin-bottom: 5px;
        }
        
        .pred-value {
            font-size: 1.8rem;
            font-weight: bold;
            margin: 5px 0;
        }
        
        .pred-gap { color: #f87171; }
        .pred-votes { color: #38bdf8; }
        .pred-cost { color: #4ade80; }
        
        .pred-unit {
            font-size: 0.75rem;
            color: #64748b;
        }
        
        /* Countdown Box */
        .countdown-box {
            background: rgba(51, 65, 85, 0.5);
            border-radius: 12px;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .countdown-label {
            color: #94a3b8;
            font-size: 0.9rem;
        }
        
        .countdown-time {
            font-size: 1.8rem;
            font-weight: bold;
            color: #fbbf24;
        }
        
        .countdown-deadline-label {
            color: #64748b;
            font-size: 0.85rem;
        }
        
        .countdown-deadline {
            font-size: 1.1rem;
            color: #e2e8f0;
        }
        
        /* Projection Section */
        .projection-section {
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(99, 102, 241, 0.15));
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(139, 92, 246, 0.3);
            margin-bottom: 15px;
        }
        
        .proj-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        
        .proj-icon {
            font-size: 1.3rem;
        }
        
        .proj-title {
            font-weight: bold;
            color: #c4b5fd;
            margin: 0;
        }
        
        .proj-note {
            font-size: 0.75rem;
            color: #64748b;
        }
        
        .proj-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        
        @media (max-width: 768px) {
            .proj-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .proj-card {
            background: rgba(15, 23, 42, 0.5);
            border-radius: 12px;
            padding: 15px;
        }
        
        .proj-scenario {
            font-size: 0.9rem;
            color: #94a3b8;
            margin-bottom: 12px;
        }
        
        .surge-input {
            width: 60px;
            padding: 5px 8px;
            border-radius: 6px;
            background: rgba(51, 65, 85, 0.8);
            border: 1px solid rgba(139, 92, 246, 0.5);
            color: #c4b5fd;
            font-weight: bold;
            text-align: center;
            margin-left: 8px;
        }
        
        .surge-x {
            color: #a78bfa;
        }
        
        .proj-item {
            margin-bottom: 12px;
        }
        
        .proj-item-blue {
            background: rgba(59, 130, 246, 0.15);
            border-radius: 10px;
            padding: 12px;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }
        
        .proj-item-label {
            font-size: 0.75rem;
            margin-bottom: 5px;
        }
        
        .ynd10-label { color: #fbbf24; }
        .ynd06-label { color: #38bdf8; }
        
        .proj-item-value {
            font-size: 1.5rem;
            font-weight: bold;
            font-family: monospace;
        }
        
        .ynd10-value { color: #fef08a; }
        .ynd06-value { color: #7dd3fc; }
        
        .proj-item-cost {
            font-size: 0.8rem;
            color: #4ade80;
            margin-top: 5px;
        }
        
        .proj-rates {
            font-size: 0.75rem;
            color: #64748b;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-top: 12px;
        }
        
        .rate-blue { color: #38bdf8; }
        .rate-yellow { color: #fbbf24; }
        
        .pred-status {
            text-align: center;
            margin-top: 15px;
            padding: 10px;
        }
        
        /* Main Grid for Standings and Chart */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 25px;
            margin-bottom: 30px;
        }
        
        @media (max-width: 1024px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }
        
        /* Standings Section */
        .standings-card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .standings-title {
            font-size: 1.3rem;
            font-weight: bold;
            color: #fbbf24;
            margin-bottom: 20px;
        }
        
        .leaderboard-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .leaderboard-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            border-radius: 12px;
            transition: transform 0.2s;
        }
        
        .leaderboard-item:hover {
            transform: scale(1.01);
        }
        
        .leaderboard-item.rank-1 {
            background: rgba(251, 191, 36, 0.15);
            border: 1px solid rgba(251, 191, 36, 0.5);
        }
        
        .leaderboard-item.rank-2 {
            background: rgba(56, 189, 248, 0.15);
            border: 1px solid rgba(56, 189, 248, 0.5);
        }
        
        .leaderboard-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .leaderboard-rank {
            font-size: 1.5rem;
            font-weight: bold;
            width: 40px;
            text-align: center;
        }
        
        .leaderboard-rank.gold { color: #fbbf24; }
        .leaderboard-rank.blue { color: #38bdf8; }
        
        .leaderboard-info .code {
            font-size: 1.1rem;
            font-weight: bold;
            color: #fff;
        }
        
        .leaderboard-info .pct {
            font-size: 0.85rem;
            margin-left: 8px;
        }
        
        .leaderboard-info .pct.gold { color: #fbbf24; }
        .leaderboard-info .pct.blue { color: #38bdf8; }
        
        .leaderboard-info .name {
            font-size: 0.75rem;
            color: #94a3b8;
            max-width: 180px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .leaderboard-right {
            text-align: right;
        }
        
        .leaderboard-votes {
            font-size: 1.2rem;
            font-weight: bold;
            color: #38bdf8;
        }
        
        .leaderboard-cost {
            font-size: 0.9rem;
            color: #4ade80;
        }
        
        /* Chart Section */
        .chart-card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .chart-title-h2h {
            font-size: 1.3rem;
            font-weight: bold;
            color: #38bdf8;
            margin: 0;
        }
        
        .chart-subtitle {
            font-size: 0.8rem;
            color: #64748b;
        }
        
        .chart-canvas-container {
            height: 300px;
            width: 100%;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 Y UNIVERSE AWARDS 2025 Vote Dashboard</h1>
            <div class="subtitle">The Best Couple - ผลโหวตแบบ Real-time</div>
            <div class="update-time" id="updateTime">กำลังโหลด...</div>
        </header>
        
        <!-- Summary Stats -->
        <div class="summary-stats" id="summaryStats">
        </div>
        
        <!-- Current Rankings -->
        <!-- Vote Package Calculator -->
        <h2 class="section-title">🛒 คำนวณการซื้อแพ็คเกจโหวต</h2>
        
        <div class="calculator-section">
            <div class="calc-input-container">
                <label for="budgetInput">💰 ใส่จำนวนเงิน (บาท):</label>
                <input type="number" id="budgetInput" placeholder="เช่น 10000" min="0">
                <button onclick="calculatePackages()" class="calc-btn">คำนวณ</button>
            </div>
            
            <div class="package-info">
                <div class="package-card">
                    <div class="pkg-price">4,000 ฿</div>
                    <div class="pkg-points">1,000 คะแนน</div>
                    <div class="pkg-rate">4 ฿/คะแนน</div>
                </div>
                <div class="package-card">
                    <div class="pkg-price">450 ฿</div>
                    <div class="pkg-points">100 คะแนน</div>
                    <div class="pkg-rate">4.5 ฿/คะแนน</div>
                </div>
                <div class="package-card">
                    <div class="pkg-price">50 ฿</div>
                    <div class="pkg-points">10 คะแนน</div>
                    <div class="pkg-rate">5 ฿/คะแนน</div>
                </div>
                <div class="package-card">
                    <div class="pkg-price">6 ฿</div>
                    <div class="pkg-points">1 คะแนน</div>
                    <div class="pkg-rate">6 ฿/คะแนน</div>
                </div>
            </div>
            
            <div class="calc-result" id="calcResult" style="display: none;">
                <div class="result-title">📋 สรุปการซื้อแพ็คเกจ</div>
                <div class="result-content" id="resultContent"></div>
                <div class="result-summary" id="resultSummary"></div>
            </div>
        </div>
        
        <!-- YND06 Victory Prediction -->
        <div class="prediction-section">
            <div class="pred-header">
                <span class="pred-icon">🎯</span>
                <h2 class="pred-title">YND06 ต้องโหวตอีกเท่าไหร่จะชนะ YND10?</h2>
            </div>
            
            <div class="pred-grid">
                <div class="pred-card">
                    <div class="pred-label">ห่างอยู่</div>
                    <div class="pred-value pred-gap" id="predGap">-</div>
                    <div class="pred-unit">คะแนน</div>
                </div>
                
                <div class="pred-card">
                    <div class="pred-label">YND06 ต้องเพิ่มอีก</div>
                    <div class="pred-value pred-votes" id="predVotes">-</div>
                    <div class="pred-unit">คะแนน (เพื่อชนะ)</div>
                </div>
                
                <div class="pred-card">
                    <div class="pred-label">ต้องใช้เงินอีก</div>
                    <div class="pred-value pred-cost" id="predCost">-</div>
                    <div class="pred-unit">บาท</div>
                </div>
            </div>
            
            <!-- Countdown -->
            <div class="countdown-box">
                <div class="countdown-left">
                    <div class="countdown-label">⏰ เหลือเวลาโหวต</div>
                    <div class="countdown-time" id="predCountdown">--:--:--</div>
                </div>
                <div class="countdown-right">
                    <div class="countdown-deadline-label">หมดเขต</div>
                    <div class="countdown-deadline">9 ม.ค. 2569 เวลา 12:00 น.</div>
                </div>
            </div>
            
            <!-- Projection Model -->
            <div class="projection-section">
                <div class="proj-header">
                    <span class="proj-icon">🔮</span>
                    <h3 class="proj-title">คาดการณ์ ณ เวลาปิดโหวต</h3>
                    <span class="proj-note">(คำนวนจากอัตราโหวต 6 ชม.ล่าสุด)</span>
                </div>
                
                <div class="proj-grid">
                    <!-- Normal Scenario -->
                    <div class="proj-card">
                        <div class="proj-scenario">📈 Scenario 1: อัตราปกติ</div>
                        
                        <div class="proj-item">
                            <div class="proj-item-label ynd10-label">YND10 จะปิดที่ประมาณ:</div>
                            <div class="proj-item-value ynd10-value" id="projYnd10Normal">-</div>
                        </div>
                        
                        <div class="proj-item-blue">
                            <div class="proj-item-label ynd06-label">YND06 ต้องโหวตเพิ่มอีก (เพื่อชนะ):</div>
                            <div class="proj-item-value ynd06-value" id="projYnd06NeededNormal">-</div>
                            <div class="proj-item-cost" id="projYnd06CostNormal">-</div>
                        </div>
                    </div>
                    
                    <!-- Surge Scenario -->
                    <div class="proj-card">
                        <div class="proj-scenario">
                            🚀 Scenario 2: สปริ้นท์ 3 ชม.สุดท้าย 
                            <input type="number" id="surgeMultiplier" value="100" min="1" max="1000" class="surge-input" onchange="recalculateSurge()">
                            <span class="surge-x">x</span>
                        </div>
                        
                        <div class="proj-item">
                            <div class="proj-item-label ynd10-label">YND10 จะปิดที่ประมาณ:</div>
                            <div class="proj-item-value ynd10-value" id="projYnd10Surge">-</div>
                        </div>
                        
                        <div class="proj-item-blue">
                            <div class="proj-item-label ynd06-label">YND06 ต้องโหวตเพิ่มอีก (เพื่อชนะ):</div>
                            <div class="proj-item-value ynd06-value" id="projYnd06NeededSurge">-</div>
                            <div class="proj-item-cost" id="projYnd06CostSurge">-</div>
                        </div>
                    </div>
                </div>
                
                <!-- Growth Rate Info -->
                <div class="proj-rates">
                    <span>📊 YND06 อัตราปัจจุบัน: <span id="projRateYnd06" class="rate-blue">-</span> votes/hr</span>
                    <span>📊 YND10 อัตราปัจจุบัน: <span id="projRateYnd10" class="rate-yellow">-</span> votes/hr</span>
                </div>
            </div>
            
            <!-- Status Message -->
            <div class="pred-status" id="predStatus">
                <!-- Dynamic status message -->
            </div>
        </div>
        
        <!-- Main Content Grid -->
        <div class="main-grid">
            <!-- Left: Current Standings -->
            <div class="standings-section">
                <div class="standings-card">
                    <h2 class="standings-title">🏆 Current Standings</h2>
                    <div id="leaderboard" class="leaderboard-container">
                        <!-- Items injected here -->
                    </div>
                </div>
            </div>
            
            <!-- Right: Head-to-Head Chart -->
            <div class="chart-section">
                <div class="chart-card">
                    <div class="chart-header">
                        <h2 class="chart-title-h2h">⚔️ Head-to-Head: YND06 vs YND10</h2>
                        <div class="chart-subtitle">Vote Growth Over Time</div>
                    </div>
                    <div class="chart-canvas-container">
                        <canvas id="h2hChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- History Section -->
        <h2 class="section-title">📈 ประวัติรายชั่วโมง (เลือกวัน)</h2>
        
        <!-- Date Selector -->
        <div class="date-selector" id="dateSelector">
            <label>📅 เลือกวัน:</label>
            <div id="dateButtons"></div>
        </div>
        
        <!-- Tabs -->
        <div class="tab-container">
            <div class="tab-buttons">
                <button class="tab-btn active" onclick="showTab('percent')">📊 เปอร์เซ็นต์ (%)</button>
                <button class="tab-btn" onclick="showTab('votes')">🎯 จำนวนโหวต</button>
                <button class="tab-btn" onclick="showTab('money')">💰 จำนวนเงิน (บาท)</button>
            </div>
            
            <!-- Percent Tab -->
            <div class="tab-content active" id="tab-percent">
                <div class="table-container" style="margin-bottom: 0;">
                    <div class="chart-title">📊 ประวัติเปอร์เซ็นต์รายชั่วโมง</div>
                    <table class="history-table" id="percentTable">
                        <thead id="percentHead"></thead>
                        <tbody id="percentBody"></tbody>
                    </table>
                </div>
            </div>
            
            <!-- Votes Tab -->
            <div class="tab-content" id="tab-votes">
                <div class="table-container" style="margin-bottom: 0;">
                    <div class="chart-title">🎯 ประวัติจำนวนโหวตรายชั่วโมง</div>
                    <table class="history-table" id="votesTable">
                        <thead id="votesHead"></thead>
                        <tbody id="votesBody"></tbody>
                    </table>
                </div>
            </div>
            
            <!-- Money Tab -->
            <div class="tab-content" id="tab-money">
                <div class="table-container" style="margin-bottom: 0;">
                    <div class="chart-title">💰 ประวัติจำนวนเงินรายชั่วโมง (บาท)</div>
                    <table class="history-table" id="moneyTable">
                        <thead id="moneyHead"></thead>
                        <tbody id="moneyBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
        

    </div>

    <div class="auto-refresh">
        <span class="pulse">🔴</span> Auto-refresh ทุก 60 วินาที
    </div>
    
    <script>
        let h2hChart;
        let allData = null;
        let selectedDate = null;
        let availableDates = [];
        let cachedProjection = null;
        
        const colors = [
            '#ff6b6b', '#feca57', '#48dbfb', '#ff9ff3', '#1dd1a1',
            '#5f27cd', '#54a0ff', '#00d2d3', '#ff9f43', '#ee5a24'
        ];
        
        // Voting Deadline: Jan 9, 2026 12:00 (Bangkok Time)
        const VOTE_DEADLINE = new Date('2026-01-09T12:00:00+07:00');
        
        // Countdown Timer
        function updateCountdown() {
            const now = new Date();
            const diff = VOTE_DEADLINE - now;
            
            if (diff <= 0) {
                document.getElementById('predCountdown').innerHTML = '<span style="color: #f87171;">หมดเวลาแล้ว!</span>';
                return;
            }
            
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);
            
            document.getElementById('predCountdown').innerText = 
                `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
        
        // Start countdown
        setInterval(updateCountdown, 1000);
        updateCountdown();
        
        function formatMoney(n) {
            return new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB', maximumFractionDigits: 0 }).format(n);
        }
        
        function recalculateSurge() {
            if (!cachedProjection) return;
            
            const multiplier = parseInt(document.getElementById('surgeMultiplier').value) || 100;
            const proj = cachedProjection;
            
            const hoursRemaining = proj.hours_remaining || 0;
            const surgeHours = Math.min(3, hoursRemaining);
            const normalHours = hoursRemaining - surgeHours;
            
            const ynd10Rate = proj.ynd10.rate_per_hour || 0;
            const ynd06Current = proj.ynd06.current || 0;
            const ynd10Current = proj.ynd10.current || 0;
            
            // Calculate YND10 closing with custom surge
            const ynd10ClosingSurge = ynd10Current + (ynd10Rate * normalHours) + (ynd10Rate * multiplier * surgeHours);
            const ynd06NeededSurge = Math.max(0, ynd10ClosingSurge - ynd06Current + 1);
            const ynd06CostSurge = ynd06NeededSurge * 4;
            
            document.getElementById('projYnd10Surge').innerText = formatNumber(Math.round(ynd10ClosingSurge));
            document.getElementById('projYnd06NeededSurge').innerText = formatNumber(Math.round(ynd06NeededSurge)) + ' โหวต';
            document.getElementById('projYnd06CostSurge').innerText = '≈ ' + formatMoney(Math.round(ynd06CostSurge));
        }
        
        function renderLeaderboard(votes) {
            if (!votes || !votes.latest_summary) return;
            
            const lb = document.getElementById('leaderboard');
            lb.innerHTML = '';
            
            // Filter to only YND10 and YND06
            const filtered = votes.latest_summary.filter(item => item.code === 'YND10' || item.code === 'YND06');
            filtered.sort((a, b) => b.points - a.points);
            
            filtered.forEach((item, index) => {
                const rankClass = index === 0 ? 'rank-1' : 'rank-2';
                const rankColor = index === 0 ? 'gold' : 'blue';
                
                // Get name from allData.current.summary
                const nameData = allData?.current?.summary?.find(s => s.code === item.code);
                const name = nameData?.names || '';
                const pct = nameData?.percentage || 0;
                
                lb.innerHTML += `
                    <div class="leaderboard-item ${rankClass}">
                        <div class="leaderboard-left">
                            <div class="leaderboard-rank ${rankColor}">#${index + 1}</div>
                            <div class="leaderboard-info">
                                <div>
                                    <span class="code">${item.code}</span>
                                    <span class="pct ${rankColor}">${pct.toFixed(2)}%</span>
                                </div>
                                <div class="name">${name}</div>
                            </div>
                        </div>
                        <div class="leaderboard-right">
                            <div class="leaderboard-votes">${formatNumber(item.points)}</div>
                            <div class="leaderboard-cost">${formatMoney(item.money)}</div>
                        </div>
                    </div>
                `;
            });
            
            // Render Prediction (YND06 vs YND10)
            const ynd06Data = votes.latest_summary.find(s => s.code === 'YND06');
            const ynd10Data = votes.latest_summary.find(s => s.code === 'YND10');
            
            if (ynd06Data && ynd10Data) {
                const gap = ynd10Data.points - ynd06Data.points;
                const votesNeeded = gap + 1; // +1 to win
                const costNeeded = votesNeeded * 4;
                
                document.getElementById('predGap').innerText = formatNumber(Math.abs(gap));
                document.getElementById('predVotes').innerText = formatNumber(votesNeeded > 0 ? votesNeeded : 0);
                document.getElementById('predCost').innerText = formatMoney(costNeeded > 0 ? costNeeded : 0);
            }
        }
        
        function calculateProjection(votes) {
            if (!votes || !votes.history || votes.history.length < 2) return;
            
            // Deadline: Jan 9, 2026 12:00
            const deadline = new Date('2026-01-09T12:00:00+07:00');
            const now = new Date();
            const hoursRemaining = Math.max(0, (deadline - now) / (1000 * 60 * 60));
            
            // Calculate hourly growth rate from last 6 hours of data
            const recent = votes.history.slice(-6);
            if (recent.length < 2) return;
            
            const first = recent[0];
            const last = recent[recent.length - 1];
            
            // Parse time strings to calculate time diff
            const parseTime = (timeStr) => {
                const parts = timeStr.split(' ');
                if (parts.length < 2) return new Date();
                const [day, month] = parts[0].split('/').map(Number);
                const [hour, min] = parts[1].split(':').map(Number);
                return new Date(2026, month - 1, day, hour, min);
            };
            
            const timeDiffHours = (parseTime(last.time) - parseTime(first.time)) / (1000 * 60 * 60);
            if (timeDiffHours <= 0) return;
            
            const ynd06First = first.codes['YND06']?.points || 0;
            const ynd06Last = last.codes['YND06']?.points || 0;
            const ynd06Rate = (ynd06Last - ynd06First) / timeDiffHours;
            
            const ynd10First = first.codes['YND10']?.points || 0;
            const ynd10Last = last.codes['YND10']?.points || 0;
            const ynd10Rate = (ynd10Last - ynd10First) / timeDiffHours;
            
            const ynd06Current = ynd06Last;
            const ynd10Current = ynd10Last;
            
            // Normal scenario
            const ynd10ClosingNormal = ynd10Current + (ynd10Rate * hoursRemaining);
            const ynd06NeededNormal = Math.max(0, ynd10ClosingNormal - ynd06Current + 1);
            const ynd06CostNormal = ynd06NeededNormal * 4;
            
            document.getElementById('projYnd10Normal').innerText = formatNumber(Math.round(ynd10ClosingNormal));
            document.getElementById('projYnd06NeededNormal').innerText = formatNumber(Math.round(ynd06NeededNormal)) + ' โหวต';
            document.getElementById('projYnd06CostNormal').innerText = '≈ ' + formatMoney(Math.round(ynd06CostNormal));
            
            // Growth rates
            document.getElementById('projRateYnd06').innerText = formatNumber(Math.round(ynd06Rate));
            document.getElementById('projRateYnd10').innerText = formatNumber(Math.round(ynd10Rate));
            
            // Cache for surge recalculation
            cachedProjection = {
                hours_remaining: hoursRemaining,
                ynd06: { current: ynd06Current, rate_per_hour: ynd06Rate },
                ynd10: { current: ynd10Current, rate_per_hour: ynd10Rate }
            };
            
            // Calculate surge
            recalculateSurge();
            
            // Status message
            const statusEl = document.getElementById('predStatus');
            if (ynd06NeededNormal <= 0) {
                statusEl.innerHTML = `<span style="font-size: 1.5rem;">🎉</span> <span style="font-size: 1.2rem; font-weight: bold; color: #38bdf8;">YND06 กำลังนำอยู่!</span>`;
            } else if (ynd06NeededNormal > 5000) {
                statusEl.innerHTML = `<span style="font-size: 1.5rem;">⚠️</span> <span style="font-size: 1.2rem; font-weight: bold; color: #fbbf24;">ต้องเร่งโหวต YND06 มากขึ้น!</span>`;
            } else {
                statusEl.innerHTML = `<span style="font-size: 1.5rem;">🔥</span> <span style="font-size: 1.2rem; font-weight: bold; color: #fb923c;">สูสี! เร่งโหวต YND06 ก่อนหมดเวลา!</span>`;
            }
        }
        
        function renderH2HChart(votes) {
            if (!votes || !votes.history || votes.history.length === 0) return;
            
            const labels = votes.history.map(h => {
                const time = h.time.split(' ')[1] || h.time;
                return time;
            });
            
            const ynd06Data = votes.history.map(h => h.codes['YND06']?.points || 0);
            const ynd10Data = votes.history.map(h => h.codes['YND10']?.points || 0);
            
            const ctx = document.getElementById('h2hChart').getContext('2d');
            
            if (h2hChart) h2hChart.destroy();
            h2hChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'YND06',
                            data: ynd06Data,
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.1)',
                            borderWidth: 3,
                            fill: true,
                            tension: 0.4
                        },
                        {
                            label: 'YND10',
                            data: ynd10Data,
                            borderColor: '#fbbf24',
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
        }
        
        // Tab switching
        function showTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');
        }
        
        function formatNumber(num) {
            return Math.round(num).toLocaleString('th-TH');
        }
        
        async function fetchAllData() {
            try {
                const [dataRes, votesRes] = await Promise.all([
                    fetch('/api/data'),
                    fetch('/api/votes')
                ]);
                
                const data = await dataRes.json();
                const votes = await votesRes.json();
                
                if (data.error) {
                    document.getElementById('statsGrid').innerHTML = 
                        '<div class="loading">❌ ' + data.error + '</div>';
                    return;
                }
                
                allData = { current: data, votes: votes };
                
                // Get available dates
                if (votes.history) {
                    const dates = new Set();
                    votes.history.forEach(h => {
                        const date = h.time.split(' ')[0];
                        dates.add(date);
                    });
                    availableDates = Array.from(dates).sort();
                    
                    if (!selectedDate && availableDates.length > 0) {
                        selectedDate = availableDates[availableDates.length - 1]; // Latest date
                    }
                }
                
                updateDashboard(data);
                updateDateButtons();
                updateVotesDisplay(votes);
                
            } catch (error) {
                console.error('Error fetching data:', error);
            }
        }
        
        function updateDateButtons() {
            let html = '';
            availableDates.forEach(date => {
                const isActive = date === selectedDate ? 'active' : '';
                html += `<button class="date-btn ${isActive}" onclick="selectDate('${date}')">${date}</button>`;
            });
            document.getElementById('dateButtons').innerHTML = html;
        }
        
        function selectDate(date) {
            selectedDate = date;
            updateDateButtons();
            if (allData && allData.votes) {
                updateVotesDisplay(allData.votes);
            }
        }
        
        function updateDashboard(data) {
            document.getElementById('updateTime').innerHTML = 
                '🕐 อัพเดทล่าสุด: ' + data.timestamp + ' | ไฟล์: ' + data.filename;
            
            const summary = data.summary;
            

            
            updateCharts(summary);
        }
        
        function updateVotesDisplay(data) {
            if (!data || data.error) return;
            
            const rates = data.rates;
            
            // Summary Stats
            let summaryHtml = `
                <div class="summary-card">
                    <div class="label">📁 จำนวนข้อมูล</div>
                    <div class="value">${data.history?.length || 0} ครั้ง</div>
                </div>
                <div class="summary-card">
                    <div class="label">🎯 ฐานโหวตรวม</div>
                    <div class="value votes-highlight">${formatNumber(data.total_base_votes)}</div>
                </div>
                <div class="summary-card">
                    <div class="label">💰 มูลค่ารวม</div>
                    <div class="value money-highlight">${formatNumber(data.total_money)} ฿</div>
                </div>
                <div class="summary-card">
                    <div class="label">📐 อัตรา</div>
                    <div class="value" style="font-size: 1rem;">1% = ${formatNumber(rates.points_per_percent)} = ${formatNumber(rates.baht_per_percent)}฿</div>
                </div>
            `;
            document.getElementById('summaryStats').innerHTML = summaryHtml;
            
            // Render new sections
            renderLeaderboard(data);
            calculateProjection(data);
            renderH2HChart(data);
            
            // Filter history by selected date
            const filteredHistory = data.history?.filter(h => {
                const date = h.time.split(' ')[0];
                return date === selectedDate;
            }) || [];
            
            if (filteredHistory.length === 0) {
                document.getElementById('percentHead').innerHTML = '<tr><th>ไม่มีข้อมูล</th></tr>';
                document.getElementById('percentBody').innerHTML = '';
                document.getElementById('votesHead').innerHTML = '<tr><th>ไม่มีข้อมูล</th></tr>';
                document.getElementById('votesBody').innerHTML = '';
                document.getElementById('moneyHead').innerHTML = '<tr><th>ไม่มีข้อมูล</th></tr>';
                document.getElementById('moneyBody').innerHTML = '';
                return;
            }
            
            const codes = data.codes || [];
            
            // Headers (show only time, not date)
            let headHtml = '<tr><th>รหัส</th>';
            filteredHistory.forEach(h => {
                const time = h.time.split(' ')[1] || h.time;
                headHtml += `<th>${time}</th>`;
            });
            headHtml += '<th>รวม/ล่าสุด</th></tr>';
            
            document.getElementById('percentHead').innerHTML = headHtml;
            document.getElementById('votesHead').innerHTML = headHtml;
            document.getElementById('moneyHead').innerHTML = headHtml;
            
            // Bodies
            let percentBodyHtml = '';
            let votesBodyHtml = '';
            let moneyBodyHtml = '';
            
            codes.forEach(code => {
                // Percent row
                percentBodyHtml += `<tr><td><strong>${code}</strong></td>`;
                let lastPct = 0;
                let prevPct = null;
                filteredHistory.forEach(h => {
                    const pct = h.codes[code]?.percentage || 0;
                    lastPct = pct;
                    
                    let changeClass = 'change-same';
                    let arrow = '';
                    if (prevPct !== null) {
                        if (pct > prevPct) { changeClass = 'change-up'; arrow = ' ↑'; }
                        else if (pct < prevPct) { changeClass = 'change-down'; arrow = ' ↓'; }
                    }
                    prevPct = pct;
                    
                    percentBodyHtml += `<td class="${changeClass}">${pct.toFixed(2)}%${arrow}</td>`;
                });
                percentBodyHtml += `<td><strong>${lastPct.toFixed(2)}%</strong></td></tr>`;
                
                // Votes row
                votesBodyHtml += `<tr><td><strong>${code}</strong></td>`;
                let lastVotes = 0;
                filteredHistory.forEach(h => {
                    const points = h.codes[code]?.points || 0;
                    const added = h.codes[code]?.points_added || 0;
                    lastVotes = points;
                    
                    let addedHtml = added > 0 ? `<br><span class="change-up">+${formatNumber(added)}</span>` : '';
                    votesBodyHtml += `<td>${formatNumber(points)}${addedHtml}</td>`;
                });
                votesBodyHtml += `<td class="votes-highlight"><strong>${formatNumber(lastVotes)}</strong></td></tr>`;
                
                // Money row
                moneyBodyHtml += `<tr><td><strong>${code}</strong></td>`;
                let lastMoney = 0;
                filteredHistory.forEach(h => {
                    const money = h.codes[code]?.money || 0;
                    const added = h.codes[code]?.money_added || 0;
                    lastMoney = money;
                    
                    let addedHtml = added > 0 ? `<br><span class="change-up">+${formatNumber(added)}</span>` : '';
                    moneyBodyHtml += `<td>${formatNumber(money)}${addedHtml}</td>`;
                });
                moneyBodyHtml += `<td class="money-highlight"><strong>${formatNumber(lastMoney)} ฿</strong></td></tr>`;
            });
            
            // Total row
            percentBodyHtml += `<tr style="background: rgba(72, 219, 251, 0.1);"><td><strong>รวม</strong></td>`;
            votesBodyHtml += `<tr style="background: rgba(72, 219, 251, 0.1);"><td><strong>ฐานรวม</strong></td>`;
            moneyBodyHtml += `<tr style="background: rgba(72, 219, 251, 0.1);"><td><strong>รวม</strong></td>`;
            
            filteredHistory.forEach(h => {
                percentBodyHtml += `<td><strong>100%</strong></td>`;
                votesBodyHtml += `<td><strong>${formatNumber(h.total_base_votes)}</strong></td>`;
                moneyBodyHtml += `<td><strong>${formatNumber(h.total_money)}</strong></td>`;
            });
            
            percentBodyHtml += `<td><strong>100%</strong></td></tr>`;
            votesBodyHtml += `<td class="votes-highlight"><strong>${formatNumber(data.total_base_votes)}</strong></td></tr>`;
            moneyBodyHtml += `<td class="money-highlight"><strong>${formatNumber(data.total_money)} ฿</strong></td></tr>`;
            
            document.getElementById('percentBody').innerHTML = percentBodyHtml;
            document.getElementById('votesBody').innerHTML = votesBodyHtml;
            document.getElementById('moneyBody').innerHTML = moneyBodyHtml;
            

        }
        
        function updateCharts(summary) {
            // Charts removed
        }
        

        
        // Initial load
        fetchAllData();
        
        // Auto-refresh every 60 seconds
        setInterval(fetchAllData, 60000);
        
        // Package Calculator
        const packages = [
            { name: 'แพ็ค 4,000 บาท', price: 4000, points: 1000 },
            { name: 'แพ็ค 450 บาท', price: 450, points: 100 },
            { name: 'แพ็ค 50 บาท', price: 50, points: 10 },
            { name: 'แพ็ค 6 บาท', price: 6, points: 1 }
        ];
        
        function calculatePackages() {
            let budget = parseInt(document.getElementById('budgetInput').value) || 0;
            
            if (budget <= 0) {
                alert('กรุณาใส่จำนวนเงินที่ต้องการ');
                return;
            }
            
            const originalBudget = budget;
            let totalPoints = 0;
            let totalSpent = 0;
            const purchases = [];
            
            // คำนวณซื้อแพ็คแพงสุดก่อน
            for (const pkg of packages) {
                const qty = Math.floor(budget / pkg.price);
                if (qty > 0) {
                    const spent = qty * pkg.price;
                    const points = qty * pkg.points;
                    
                    purchases.push({
                        name: pkg.name,
                        price: pkg.price,
                        qty: qty,
                        spent: spent,
                        points: points
                    });
                    
                    budget -= spent;
                    totalSpent += spent;
                    totalPoints += points;
                }
            }
            
            // แสดงผล
            const resultDiv = document.getElementById('calcResult');
            const contentDiv = document.getElementById('resultContent');
            const summaryDiv = document.getElementById('resultSummary');
            
            if (purchases.length === 0) {
                contentDiv.innerHTML = '<p style="color: #ff6b6b;">เงินไม่พอซื้อแพ็คใดๆ (ต้องมีอย่างน้อย 6 บาท)</p>';
                summaryDiv.innerHTML = '';
            } else {
                let contentHtml = '';
                purchases.forEach(p => {
                    contentHtml += `
                        <div class="result-item">
                            <span class="pkg-name">${p.name}</span>
                            <span class="pkg-qty">x ${p.qty}</span>
                            <span class="pkg-subtotal">${formatNumber(p.spent)} ฿</span>
                            <span class="pkg-points-total">${formatNumber(p.points)} คะแนน</span>
                        </div>
                    `;
                });
                contentDiv.innerHTML = contentHtml;
                
                summaryDiv.innerHTML = `
                    <div class="summary-row">
                        <span>💰 เงินที่ใส่:</span>
                        <span>${formatNumber(originalBudget)} บาท</span>
                    </div>
                    <div class="summary-row">
                        <span>🛒 เงินที่ใช้:</span>
                        <span class="money-highlight">${formatNumber(totalSpent)} บาท</span>
                    </div>
                    <div class="summary-total">
                        <span>🎯 คะแนนที่ได้รับ: </span>
                        <span class="points">${formatNumber(totalPoints)} คะแนน</span>
                    </div>
                    ${budget > 0 ? `<div class="summary-remaining">💸 เงินคงเหลือ: ${formatNumber(budget)} บาท (ไม่พอซื้อแพ็คใดๆ)</div>` : ''}
                `;
            }
            
            resultDiv.style.display = 'block';
        }
        
        // Enter key to calculate
        document.getElementById('budgetInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                calculatePackages();
            }
        });
    </script>
</body>
</html>
'''

def get_latest_data():
    """ดึงข้อมูลล่าสุดจากไฟล์ JSON"""
    try:
        # หาไฟล์ JSON ล่าสุด
        json_files = sorted(DATA_DIR.glob('vote_*.json'), reverse=True)
        
        if not json_files:
            return {'error': 'ไม่พบไฟล์ข้อมูล - รัน scraper ก่อน'}
        
        latest_file = json_files[0]
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        data['filename'] = latest_file.name
        return data
        
    except Exception as e:
        return {'error': str(e)}


def get_all_history():
    """ดึงประวัติข้อมูลทั้งหมด"""
    try:
        json_files = sorted(DATA_DIR.glob('vote_*.json'))
        
        if not json_files:
            return {'error': 'ไม่พบไฟล์ข้อมูล'}
        
        history = []
        all_codes = set()
        
        for file in json_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # แปลง timestamp เป็นเวลาที่อ่านง่าย
                timestamp = data.get('timestamp', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        time_str = dt.strftime('%d/%m %H:%M')
                    except:
                        time_str = timestamp[:16]
                else:
                    # ดึงเวลาจากชื่อไฟล์
                    time_str = file.stem.replace('vote_', '')
                
                # สร้าง dict ของ code -> percentage
                vote_data = {}
                if 'summary' in data:
                    for item in data['summary']:
                        code = item.get('code', '')
                        pct = item.get('percentage', 0)
                        vote_data[code] = pct
                        all_codes.add(code)
                
                history.append({
                    'time': time_str,
                    'filename': file.name,
                    'data': vote_data
                })
                
            except Exception as e:
                continue
        
        # เรียง codes
        codes = sorted(list(all_codes))
        
        return {
            'history': history,
            'codes': codes,
            'total_files': len(history)
        }
        
    except Exception as e:
        return {'error': str(e)}


def calculate_votes_and_money():
    """
    คำนวณคะแนนและเงินจาก % ที่เปลี่ยนแปลง
    สูตร Cumulative Gain Only: นับเฉพาะ % ที่เพิ่มขึ้นเป็นคะแนนสะสม
    1% = 1000 คะแนน = 4000 บาท
    """
    try:
        json_files = sorted(DATA_DIR.glob('vote_*.json'))
        
        if not json_files:
            return {'error': 'ไม่พบไฟล์ข้อมูล'}
        
        # อัตราแปลง
        POINTS_PER_PERCENT = 1000  # 1% = 1000 คะแนน
        BAHT_PER_POINT = 4  # 1 คะแนน = 4 บาท
        BASE_TOTAL_VOTES = 100000  # ฐานคะแนนสำหรับแปลง % เป็นโหวต
        
        all_codes = set()
        history_data = []
        
        # โหลดข้อมูลทั้งหมดก่อน
        for file in json_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                timestamp = data.get('timestamp', '')
                raw_timestamp = timestamp  # Keep for sorting
                
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        time_str = dt.strftime('%d/%m %H:%M')
                    except:
                        time_str = timestamp[:16]
                else:
                    time_str = file.stem.replace('vote_', '')
                    raw_timestamp = time_str  # Fallback for sorting
                
                vote_data = {}
                if 'summary' in data:
                    for item in data['summary']:
                        code = item.get('code', '')
                        pct = item.get('percentage', 0)
                        vote_data[code] = pct
                        all_codes.add(code)
                
                history_data.append({
                    'time': time_str,
                    'raw_timestamp': raw_timestamp,
                    'data': vote_data
                })
            except:
                continue
        
        if not history_data:
            return {'error': 'ไม่มีข้อมูล'}
        
        # Sort by timestamp to match dashboard_two.py
        history_data.sort(key=lambda x: x['raw_timestamp'])
        
        print(f"DEBUG: dashboard.py loaded {len(history_data)} records")
        if history_data:
            print(f"DEBUG: First: {history_data[0]['raw_timestamp']}, Last: {history_data[-1]['raw_timestamp']}")
        
        codes = sorted(list(all_codes))
        
        # Cumulative Gain Only: นับเฉพาะ % ที่เพิ่มขึ้น
        cumulative_points = {code: 0.0 for code in codes}
        prev_pct = {code: 0.0 for code in codes}
        
        result_history = []
        
        for i, entry in enumerate(history_data):
            current_pct = entry['data']
            time_str = entry['time']
            
            hour_data = {
                'time': time_str,
                'codes': {}
            }
            
            # Cumulative Gain Only: นับเฉพาะ % ที่เพิ่มขึ้น
            for code in codes:
                curr = current_pct.get(code, 0)
                prev = prev_pct.get(code, 0)
                
                # นับเฉพาะ % ที่เพิ่มขึ้น
                points_added = 0
                if curr > prev:
                    delta = curr - prev
                    points_added = (delta / 100) * BASE_TOTAL_VOTES
                    cumulative_points[code] += points_added
                
                points = cumulative_points[code]
                money = points * BAHT_PER_POINT
                
                hour_data['codes'][code] = {
                    'percentage': curr,
                    'points': round(points),
                    'money': round(money),
                    'points_added': round(points_added),
                    'money_added': round(points_added * BAHT_PER_POINT)
                }
                
                prev_pct[code] = curr
            
            total_points = sum(cumulative_points.values())
            hour_data['total_base_votes'] = round(total_points)
            hour_data['total_money'] = round(total_points * BAHT_PER_POINT)
            
            result_history.append(hour_data)
        
        # สรุปล่าสุด
        latest_summary = []
        for code in codes:
            latest_summary.append({
                'code': code,
                'points': round(cumulative_points[code]),
                'money': round(cumulative_points[code] * BAHT_PER_POINT)
            })
        
        latest_summary.sort(key=lambda x: x['points'], reverse=True)
        
        # Debug: Print YND06 and YND10 values
        for item in latest_summary:
            if item['code'] in ['YND06', 'YND10']:
                print(f"DEBUG API: {item['code']} = {item['points']}")
        
        total_votes = sum(cumulative_points.values())
        
        return {
            'history': result_history,
            'codes': codes,
            'latest_summary': latest_summary,
            'total_base_votes': round(total_votes),
            'total_money': round(total_votes * BAHT_PER_POINT),
            'rates': {
                'points_per_percent': POINTS_PER_PERCENT,
                'baht_per_point': BAHT_PER_POINT,
                'baht_per_percent': POINTS_PER_PERCENT * BAHT_PER_POINT
            }
        }
        
    except Exception as e:
        return {'error': str(e)}


@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/data')
def api_data():
    return jsonify(get_latest_data())

@app.route('/api/history')
def api_history():
    return jsonify(get_all_history())

@app.route('/api/votes')
def api_votes():
    return jsonify(calculate_votes_and_money())

@app.route('/api/scrape')
def api_scrape():
    """Trigger scraper manually"""
    try:
        success = scraper.run_once()
        if success:
            return jsonify({'status': 'success', 'message': 'ดึงข้อมูลสำเร็จ'})
        else:
            return jsonify({'status': 'error', 'message': 'ดึงข้อมูลไม่สำเร็จ'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# Start scraper when app starts
with app.app_context():
    start_scraper()

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Y UNIVERSE AWARDS 2025 Dashboard")
    print("=" * 50)
    
    # Start scraper thread
    start_scraper()
    
    print("📊 เปิด browser ไปที่: http://localhost:8080")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=8080, debug=False)