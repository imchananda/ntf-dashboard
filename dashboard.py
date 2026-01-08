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
        <div class="stats-grid" id="statsGrid">
            <div class="loading">กำลังโหลดข้อมูล...</div>
        </div>
        
        <!-- Current Summary Table -->
        <div class="table-container">
            <div class="chart-title">📋 สรุปอันดับปัจจุบัน (%, คะแนน, เงิน)</div>
            <table id="summaryTable">
                <thead>
                    <tr>
                        <th>อันดับ</th>
                        <th>รหัส</th>
                        <th>ชื่อคู่</th>
                        <th>% ล่าสุด</th>
                        <th>คะแนนสะสม</th>
                        <th>มูลค่า (บาท)</th>
                        <th>สัดส่วน</th>
                    </tr>
                </thead>
                <tbody id="summaryBody">
                </tbody>
            </table>
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
        
        <!-- Timeline Chart -->
        <div class="table-container" style="margin-top: 30px;">
            <div class="chart-title">📉 กราฟแนวโน้มคะแนน (วันที่เลือก)</div>
            <canvas id="timelineChart" height="80"></canvas>
        </div>
        
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
    </div>

    <div class="auto-refresh">
        <span class="pulse">🔴</span> Auto-refresh ทุก 60 วินาที
    </div>
    
    <script>
        let timelineChart;
        let allData = null;
        let selectedDate = null;
        let availableDates = [];
        
        const colors = [
            '#ff6b6b', '#feca57', '#48dbfb', '#ff9ff3', '#1dd1a1',
            '#5f27cd', '#54a0ff', '#00d2d3', '#ff9f43', '#ee5a24'
        ];
        
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
            
            // Stats Cards
            let statsHtml = '';
            summary.forEach((item, index) => {
                const isLeader = index === 0;
                statsHtml += `
                    <div class="stat-card ${isLeader ? 'leader' : ''}">
                        <div class="rank">${isLeader ? '👑 #1' : '#' + (index + 1)}</div>
                        <div class="code">${item.code}</div>
                        <div class="percentage">${item.percentage.toFixed(2)}%</div>
                        <div class="names">${item.names}</div>
                    </div>
                `;
            });
            document.getElementById('statsGrid').innerHTML = statsHtml;
            
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
            
            // Summary Table with votes and money
            let summaryBodyHtml = '';
            if (data.latest_summary && allData.current.summary) {
                allData.current.summary.forEach((item, index) => {
                    const rankClass = index === 0 ? 'rank-1' : index === 1 ? 'rank-2' : index === 2 ? 'rank-3' : 'rank-other';
                    const voteData = data.latest_summary.find(v => v.code === item.code) || {};
                    
                    summaryBodyHtml += `
                        <tr>
                            <td><span class="rank-badge ${rankClass}">${index + 1}</span></td>
                            <td><strong>${item.code}</strong></td>
                            <td style="font-size: 0.85rem;">${item.names}</td>
                            <td><strong>${item.percentage.toFixed(2)}%</strong></td>
                            <td class="votes-highlight">${formatNumber(voteData.points || 0)}</td>
                            <td class="money-highlight">${formatNumber(voteData.money || 0)} ฿</td>
                            <td>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${item.percentage}%"></div>
                                </div>
                            </td>
                        </tr>
                    `;
                });
            }
            document.getElementById('summaryBody').innerHTML = summaryBodyHtml;
            
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
            
            // Timeline Chart for selected date
            updateTimelineChart(filteredHistory, codes);
        }
        
        function updateCharts(summary) {
            // Charts removed
        }
        
        function updateTimelineChart(history, codes) {
            if (!history || history.length === 0) return;
            
            const labels = history.map(h => {
                const time = h.time.split(' ')[1] || h.time;
                return time;
            });
            
            const datasets = codes.map((code, index) => ({
                label: code,
                data: history.map(h => h.codes[code]?.percentage || 0),
                borderColor: colors[index % colors.length],
                backgroundColor: 'transparent',
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 3
            }));
            
            if (timelineChart) timelineChart.destroy();
            timelineChart = new Chart(document.getElementById('timelineChart'), {
                type: 'line',
                data: { labels, datasets },
                options: {
                    responsive: true,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#fff', padding: 10, usePointStyle: true } }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#fff' } },
                        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#fff' } }
                    }
                }
            });
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