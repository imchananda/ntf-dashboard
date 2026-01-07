"""
YNA2025 Vote Summary Scraper
ดึงข้อมูลผลโหวตจากหน้า votesummary.php
รองรับกราฟ Chart.js
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import logging
from datetime import datetime
from pathlib import Path
import schedule
import time
import csv

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('yna2025_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class YNA2025Scraper:
    """Scraper สำหรับดึงผลโหวต YNA2025"""
    
    def __init__(self, config_path: str = 'config_yna2025.json'):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.session = requests.Session()
        self.is_logged_in = False
        
        # Headers เหมือน browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'th,en;q=0.9',
            'Referer': 'https://acmonlinebiz.com/yna2025/',
        })
        
        # สร้างโฟลเดอร์เก็บข้อมูล
        self.output_dir = Path(self.config.get('output_dir', 'data_yna2025'))
        self.output_dir.mkdir(exist_ok=True)
        
    def login(self) -> bool:
        """Login เข้าระบบ"""
        try:
            login_page = self.config.get('login_page', self.config['login_url'])
            login_url = self.config['login_url']
            
            # เข้าหน้า login ก่อนเพื่อเก็บ cookies
            self.session.get(login_page, timeout=30)
            
            # ส่ง login request
            payload = {
                self.config.get('username_field', 'username'): self.config['username'],
                self.config.get('password_field', 'userpassword'): self.config['password'],
            }
            
            response = self.session.post(
                login_url,
                data=payload,
                timeout=30,
                allow_redirects=True
            )
            
            # ตรวจสอบว่า login สำเร็จ
            if 'login' not in response.url.lower() or 'dashboard' in response.url.lower():
                self.is_logged_in = True
                logger.info("✅ Login สำเร็จ")
                return True
            else:
                # ตรวจสอบ cookies
                if self.session.cookies.get_dict():
                    self.is_logged_in = True
                    logger.info("✅ Login สำเร็จ (มี session cookies)")
                    return True
                    
            logger.error("❌ Login ไม่สำเร็จ")
            return False
            
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False
    
    def fetch_vote_data(self) -> dict | None:
        """ดึงข้อมูลผลโหวต"""
        if not self.is_logged_in:
            if not self.login():
                return None
        
        try:
            data_url = self.config['data_url']
            response = self.session.get(data_url, timeout=30)
            
            # ตรวจสอบว่าถูก redirect กลับ login หรือไม่
            if 'login' in response.url.lower():
                logger.warning("⚠️ Session หมดอายุ - กำลัง login ใหม่...")
                self.is_logged_in = False
                if not self.login():
                    return None
                response = self.session.get(data_url, timeout=30)
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # ดึงข้อมูลจาก Chart.js
            vote_data = self._extract_chart_data(html)
            
            # ดึงข้อมูลจาก list รายชื่อคู่
            couples = self._extract_couple_names(soup)
            
            # รวมข้อมูล
            result = {
                'timestamp': datetime.now().isoformat(),
                'url': data_url,
                'category': self._extract_category(soup),
                'votes': vote_data,
                'couples': couples,
            }
            
            # รวมข้อมูล votes กับชื่อคู่
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
                
                # เรียงตาม % มากไปน้อย
                result['summary'].sort(key=lambda x: x['percentage'], reverse=True)
                result['ranking'] = [
                    f"#{i+1} {item['code']}: {item['percentage']}% - {item['names']}"
                    for i, item in enumerate(result['summary'])
                ]
            
            logger.info(f"✅ ดึงข้อมูลสำเร็จ - พบ {len(vote_data.get('labels', []))} รายการ")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error fetching data: {e}")
            return None
    
    def _extract_category(self, soup: BeautifulSoup) -> str:
        """ดึงชื่อหมวดหมู่"""
        # หาจาก header หรือ title
        header = soup.find(['h1', 'h2', 'h3'], class_=lambda x: x and 'header' in str(x).lower())
        if header:
            return header.get_text(strip=True)
        
        # หาจาก div ที่มี style เฉพาะ
        title_div = soup.find('div', style=lambda x: x and 'background' in str(x).lower())
        if title_div:
            return title_div.get_text(strip=True)
            
        return "The Best Couple"
    
    def _extract_chart_data(self, html: str) -> dict:
        """ดึงข้อมูลจาก Chart.js script"""
        result = {'labels': [], 'data': []}
        
        # หา script ที่มี Chart.js
        soup = BeautifulSoup(html, 'html.parser')
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string and 'Chart' in script.string:
                script_text = script.string
                
                # หา labels: ["YND01","YND02",...]
                labels_match = re.search(r'labels\s*:\s*\[(.*?)\]', script_text, re.DOTALL)
                if labels_match:
                    labels_str = labels_match.group(1)
                    result['labels'] = re.findall(r'["\']([^"\']+)["\']', labels_str)
                
                # หา data: ["0.32","0.33",...] หรือ data: [0.32, 0.33,...]
                # รองรับทั้งแบบ string และ number
                data_match = re.search(r"data\s*:\s*\[(.*?)\]", script_text, re.DOTALL)
                if data_match:
                    data_str = data_match.group(1)
                    # หาตัวเลขทั้งแบบ "0.32" และ 0.32
                    numbers = re.findall(r'["\']?([\d.]+)["\']?', data_str)
                    result['data'] = [float(x) for x in numbers if x]
                
                if result['labels'] and result['data']:
                    break
        
        return result
    
    def _extract_couple_names(self, soup: BeautifulSoup) -> dict:
        """ดึงรายชื่อคู่จาก list"""
        couples = {}
        
        # หา list items ที่มีรหัส YND
        for li in soup.find_all('li'):
            text = li.get_text(strip=True)
            # Pattern: YND01 : ชื่อ1 ชื่อ2 - series
            match = re.match(r'(YND\d+)\s*:\s*(.+?)(?:\s*\((.+?)\))?$', text)
            if match:
                code = match.group(1)
                names = match.group(2).strip()
                series = match.group(3) if match.group(3) else ''
                couples[code] = {
                    'names': names,
                    'series': series
                }
        
        # ถ้าหาจาก li ไม่เจอ ลองหาจาก text ทั้งหมด
        if not couples:
            text = soup.get_text()
            for match in re.finditer(r'(YND\d+)\s*:\s*([^\n]+)', text):
                code = match.group(1)
                rest = match.group(2).strip()
                # แยก series ออก
                series_match = re.search(r'\(([^)]+)\)\s*$', rest)
                if series_match:
                    series = series_match.group(1)
                    names = rest[:series_match.start()].strip()
                else:
                    series = ''
                    names = rest
                
                couples[code] = {
                    'names': names,
                    'series': series
                }
        
        return couples
    
    def save_data(self, data: dict) -> str:
        """บันทึกข้อมูล"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # บันทึก JSON
        json_file = self.output_dir / f"vote_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # บันทึก CSV (summary)
        if 'summary' in data:
            csv_file = self.output_dir / f"vote_{timestamp}.csv"
            with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['code', 'percentage', 'names', 'series'])
                writer.writeheader()
                writer.writerows(data['summary'])
            logger.info(f"💾 บันทึก CSV: {csv_file}")
        
        # บันทึก ranking ล่าสุดแยกไฟล์ (overwrite)
        if 'ranking' in data:
            ranking_file = self.output_dir / "latest_ranking.txt"
            with open(ranking_file, 'w', encoding='utf-8') as f:
                f.write(f"The Best Couple - อัพเดท: {data['timestamp']}\n")
                f.write("=" * 50 + "\n")
                for rank in data['ranking']:
                    f.write(rank + "\n")
        
        logger.info(f"💾 บันทึก JSON: {json_file}")
        return str(json_file)
    
    def run_once(self) -> bool:
        """ดึงข้อมูลครั้งเดียว"""
        data = self.fetch_vote_data()
        if data:
            self.save_data(data)
            
            # แสดง ranking
            if 'ranking' in data:
                print("\n📊 ผลโหวตล่าสุด:")
                print("-" * 50)
                for rank in data['ranking']:  # แสดงทั้งหมด
                    print(rank)
                print("-" * 50)
            
            return True
        return False
    
    def run_scheduled(self, interval_hours: int = 1):
        """รันแบบ schedule"""
        logger.info(f"🚀 เริ่มระบบดึงผลโหวตทุก {interval_hours} ชั่วโมง")
        
        # รันครั้งแรก
        self.run_once()
        
        # ตั้ง schedule
        schedule.every(interval_hours).hours.do(self.run_once)
        
        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='YNA2025 Vote Scraper')
    parser.add_argument('-c', '--config', default='config_yna2025.json', help='Config file')
    parser.add_argument('-o', '--once', action='store_true', help='Run once')
    parser.add_argument('-i', '--interval', type=int, default=1, help='Interval in hours')
    
    args = parser.parse_args()
    
    scraper = YNA2025Scraper(args.config)
    
    if args.once:
        scraper.run_once()
    else:
        try:
            scraper.run_scheduled(args.interval)
        except KeyboardInterrupt:
            print("\n👋 หยุดการทำงาน")


if __name__ == "__main__":
    main()