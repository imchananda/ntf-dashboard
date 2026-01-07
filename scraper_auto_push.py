"""
Y UNIVERSE AWARDS 2025 - Auto Scraper with GitHub Push
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from pathlib import Path
import subprocess
import time
import schedule

# ========== ตั้งค่า ==========
CONFIG = {
    'username': 'chan.kwoninine@gmail.com',           # ← เปลี่ยนเป็น email ของคุณ
    'password': 'ธฟำโฟืัๅๅต/',        # ← เปลี่ยนเป็น password ของคุณ
    'login_url': 'https://acmonlinebiz.com/yna2025/login_action.php',
    'login_page': 'https://acmonlinebiz.com/yna2025/login.php',
    'data_url': 'https://acmonlinebiz.com/yna2025/votesummary.php?tpid=4',
    'interval_hours': 1,
}

DATA_DIR = Path('data_yna2025')
DATA_DIR.mkdir(exist_ok=True)

class VoteScraper:
    def __init__(self):
        self.session = requests.Session()
        self.is_logged_in = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
    
    def login(self):
        try:
            print("🔐 กำลัง login...")
            self.session.get(CONFIG['login_page'], timeout=30)
            payload = {'username': CONFIG['username'], 'userpassword': CONFIG['password']}
            response = self.session.post(CONFIG['login_url'], data=payload, timeout=30, allow_redirects=True)
            if 'login' not in response.url.lower() or self.session.cookies.get_dict():
                self.is_logged_in = True
                print("✅ Login สำเร็จ")
                return True
            print("❌ Login ไม่สำเร็จ")
            return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def fetch_data(self):
        if not self.is_logged_in and not self.login():
            return None
        try:
            response = self.session.get(CONFIG['data_url'], timeout=30)
            if 'login' in response.url.lower():
                self.is_logged_in = False
                if not self.login():
                    return None
                response = self.session.get(CONFIG['data_url'], timeout=30)
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            vote_data = {'labels': [], 'data': []}
            for script in soup.find_all('script'):
                if script.string and 'Chart' in script.string:
                    labels_match = re.search(r'labels\s*:\s*\[(.*?)\]', script.string, re.DOTALL)
                    if labels_match:
                        vote_data['labels'] = re.findall(r'["\']([^"\']+)["\']', labels_match.group(1))
                    data_match = re.search(r"data\s*:\s*\[(.*?)\]", script.string, re.DOTALL)
                    if data_match:
                        numbers = re.findall(r'["\']?([\d.]+)["\']?', data_match.group(1))
                        vote_data['data'] = [float(x) for x in numbers if x]
                    break
            
            couples = {}
            for match in re.finditer(r'(YND\d+)\s*:\s*([^\n]+)', soup.get_text()):
                code, rest = match.group(1), match.group(2).strip()
                series_match = re.search(r'\(([^)]+)\)\s*$', rest)
                couples[code] = {
                    'names': rest[:series_match.start()].strip() if series_match else rest,
                    'series': series_match.group(1) if series_match else ''
                }
            
            result = {'timestamp': datetime.now().isoformat(), 'votes': vote_data, 'couples': couples, 'summary': []}
            for i, label in enumerate(vote_data['labels']):
                couple_info = couples.get(label, {})
                result['summary'].append({
                    'code': label,
                    'percentage': vote_data['data'][i] if i < len(vote_data['data']) else 0,
                    'names': couple_info.get('names', ''),
                    'series': couple_info.get('series', ''),
                })
            result['summary'].sort(key=lambda x: x['percentage'], reverse=True)
            print("✅ ดึงข้อมูลสำเร็จ")
            return result
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def save_data(self, data):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = DATA_DIR / f"vote_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 บันทึก: {json_file.name}")
        return str(json_file)

def git_push():
    try:
        print("📤 กำลัง push ขึ้น GitHub...")
        subprocess.run(['git', 'add', 'data_yna2025/'], check=True, capture_output=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        result = subprocess.run(['git', 'commit', '-m', f'Update vote data - {timestamp}'], capture_output=True, text=True)
        if 'nothing to commit' in result.stdout + result.stderr:
            print("ℹ️ ไม่มีการเปลี่ยนแปลง")
            return True
        subprocess.run(['git', 'push'], check=True, capture_output=True)
        print("✅ Push สำเร็จ")
        return True
    except Exception as e:
        print(f"❌ Git error: {e}")
        return False

def run_job():
    print(f"\n{'='*50}")
    print(f"🔄 เริ่มดึงข้อมูล - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('='*50)
    scraper = VoteScraper()
    data = scraper.fetch_data()
    if data:
        scraper.save_data(data)
        print("\n📊 ผลโหวตปัจจุบัน:")
        for item in data['summary'][:3]:
            print(f"   {item['code']}: {item['percentage']:.2f}%")
        git_push()
    print(f"\n⏰ รอดึงข้อมูลครั้งต่อไปใน {CONFIG['interval_hours']} ชั่วโมง...")

if __name__ == '__main__':
    print("="*50)
    print("🚀 Y UNIVERSE AWARDS 2025 - Auto Scraper")
    print("="*50)
    run_job()
    schedule.every(CONFIG['interval_hours']).hours.do(run_job)
    while True:
        schedule.run_pending()
        time.sleep(60)