"""
ระบบดึงข้อมูลจากเว็บที่ต้อง Login (Session-based)
- Login และเก็บ session/cookies
- ดึงข้อมูลทุกชั่วโมง
- บันทึกเป็นไฟล์ JSON/CSV
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
import os
import logging
from datetime import datetime
from pathlib import Path
import schedule
import time
import hashlib

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WebScraper:
    """คลาสหลักสำหรับดึงข้อมูลจากเว็บที่ต้อง login"""
    
    def __init__(self, config: dict):
        """
        Args:
            config: dictionary ที่มี keys:
                - login_url: URL หน้า login
                - data_url: URL หน้าข้อมูลที่ต้องการดึง
                - username: ชื่อผู้ใช้
                - password: รหัสผ่าน
                - username_field: ชื่อ field username ใน form (default: 'username')
                - password_field: ชื่อ field password ใน form (default: 'password')
                - output_dir: โฟลเดอร์เก็บข้อมูล (default: 'data')
        """
        self.config = config
        self.session = requests.Session()
        self.is_logged_in = False
        
        # ตั้งค่า headers ให้เหมือน browser จริง
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'th,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # สร้างโฟลเดอร์เก็บข้อมูล
        self.output_dir = Path(config.get('output_dir', 'data'))
        self.output_dir.mkdir(exist_ok=True)
        
    def get_csrf_token(self, url: str = None) -> dict:
        """ดึง CSRF token และ hidden fields จากหน้า login"""
        try:
            # ใช้ login_page ถ้ามี (หน้าที่แสดง form) หรือใช้ url ที่ส่งมา
            page_url = url or self.config.get('login_page') or self.config['login_url']
            
            response = self.session.get(page_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            hidden_fields = {}
            
            # หา hidden inputs ทั้งหมด (รวม CSRF token)
            for hidden in soup.find_all('input', type='hidden'):
                name = hidden.get('name')
                value = hidden.get('value', '')
                if name:
                    hidden_fields[name] = value
                    
            # หา CSRF token จาก meta tag (บางเว็บใช้แบบนี้)
            csrf_meta = soup.find('meta', {'name': ['csrf-token', '_token', 'csrf_token']})
            if csrf_meta:
                hidden_fields['_token'] = csrf_meta.get('content', '')
                
            logger.info(f"พบ hidden fields: {list(hidden_fields.keys())}")
            return hidden_fields
            
        except Exception as e:
            logger.error(f"ไม่สามารถดึง CSRF token: {e}")
            return {}
    
    def login(self) -> bool:
        """Login เข้าระบบ"""
        try:
            # login_url = URL ที่ส่ง POST (form action)
            # login_page = URL หน้า login ที่แสดง form (ถ้าแยกกัน)
            login_url = self.config['login_url']
            login_page = self.config.get('login_page', login_url)
            
            # ดึง CSRF token และ hidden fields จากหน้า login ก่อน
            hidden_fields = self.get_csrf_token(login_page)
            
            # สร้าง payload สำหรับ login
            payload = {
                self.config.get('username_field', 'username'): self.config['username'],
                self.config.get('password_field', 'password'): self.config['password'],
                **hidden_fields  # รวม hidden fields ทั้งหมด
            }
            
            # ส่ง POST request เพื่อ login
            response = self.session.post(
                login_url,
                data=payload,
                timeout=30,
                allow_redirects=True
            )
            
            # ตรวจสอบว่า login สำเร็จหรือไม่
            if self._check_login_success(response):
                self.is_logged_in = True
                logger.info("✅ Login สำเร็จ")
                return True
            else:
                logger.error("❌ Login ไม่สำเร็จ - ตรวจสอบ username/password")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการ login: {e}")
            return False
    
    def _check_login_success(self, response) -> bool:
        """ตรวจสอบว่า login สำเร็จหรือไม่"""
        # วิธีตรวจสอบหลายแบบ
        
        login_url = self.config['login_url']
        login_page = self.config.get('login_page', login_url)
        
        # 1. ตรวจสอบ URL (ถ้า redirect ออกจากหน้า login = สำเร็จ)
        if login_url not in response.url and login_page not in response.url:
            return True
            
        # 2. ตรวจสอบ cookies
        if 'session' in self.session.cookies.get_dict() or \
           'PHPSESSID' in self.session.cookies.get_dict() or \
           'laravel_session' in self.session.cookies.get_dict():
            return True
            
        # 3. ตรวจสอบเนื้อหา (ไม่มีข้อความ error)
        soup = BeautifulSoup(response.text, 'html.parser')
        error_keywords = ['ผิดพลาด', 'incorrect', 'invalid', 'error', 'failed', 'ไม่ถูกต้อง']
        page_text = soup.get_text().lower()
        
        for keyword in error_keywords:
            if keyword in page_text:
                return False
                
        return True
    
    def fetch_data(self) -> dict | None:
        """ดึงข้อมูลจากหน้าที่ต้องการ"""
        if not self.is_logged_in:
            if not self.login():
                return None
        
        try:
            data_url = self.config['data_url']
            response = self.session.get(data_url, timeout=30)
            
            # ถ้าถูก redirect กลับไปหน้า login = session หมดอายุ
            login_page = self.config.get('login_page', self.config['login_url'])
            if self.config['login_url'] in response.url or login_page in response.url:
                logger.warning("⚠️ Session หมดอายุ - กำลัง login ใหม่...")
                self.is_logged_in = False
                if self.login():
                    response = self.session.get(data_url, timeout=30)
                else:
                    return None
            
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ดึงข้อมูลตาม selector ที่กำหนด (ถ้ามี)
            data = self._extract_data(soup, response.text)
            
            logger.info(f"✅ ดึงข้อมูลสำเร็จ จาก {data_url}")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
            return None
    
    def _extract_data(self, soup: BeautifulSoup, raw_html: str) -> dict:
        """แยกข้อมูลจาก HTML - ปรับแต่งตามเว็บที่ต้องการ"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'url': self.config['data_url'],
        }
        
        # ถ้ากำหนด CSS selector มา
        if 'selectors' in self.config:
            for name, selector in self.config['selectors'].items():
                elements = soup.select(selector)
                if elements:
                    if len(elements) == 1:
                        data[name] = elements[0].get_text(strip=True)
                    else:
                        data[name] = [el.get_text(strip=True) for el in elements]
        
        # ดึงตารางทั้งหมด (ถ้ามี)
        tables = soup.find_all('table')
        if tables:
            data['tables'] = []
            for i, table in enumerate(tables):
                table_data = self._parse_table(table)
                if table_data:
                    data['tables'].append({
                        'table_index': i,
                        'rows': table_data
                    })
        
        # เก็บ raw HTML ด้วย (optional)
        if self.config.get('save_raw_html', False):
            data['raw_html'] = raw_html
            
        return data
    
    def _parse_table(self, table) -> list:
        """แปลงตาราง HTML เป็น list of dicts"""
        rows = []
        headers = []
        
        # หา headers
        header_row = table.find('thead') or table.find('tr')
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        
        # หา data rows
        tbody = table.find('tbody') or table
        for tr in tbody.find_all('tr')[1:] if not table.find('thead') else tbody.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells and len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
            elif cells:
                rows.append(cells)
                
        return rows
    
    def save_data(self, data: dict, format: str = 'json') -> str:
        """บันทึกข้อมูลลงไฟล์"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == 'json':
            filename = self.output_dir / f"data_{timestamp}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        elif format == 'csv':
            filename = self.output_dir / f"data_{timestamp}.csv"
            # ถ้ามีตาราง ให้บันทึกตารางแรก
            if 'tables' in data and data['tables']:
                rows = data['tables'][0].get('rows', [])
                if rows and isinstance(rows[0], dict):
                    with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)
            else:
                # บันทึกเป็น flat data
                with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=data.keys())
                    writer.writeheader()
                    writer.writerow(data)
        
        logger.info(f"💾 บันทึกข้อมูลที่: {filename}")
        return str(filename)
    
    def run_once(self) -> bool:
        """ดึงข้อมูลครั้งเดียว"""
        data = self.fetch_data()
        if data:
            self.save_data(data, self.config.get('output_format', 'json'))
            return True
        return False
    
    def run_scheduled(self, interval_hours: int = 1):
        """รันแบบ schedule ทุก X ชั่วโมง"""
        logger.info(f"🚀 เริ่มระบบดึงข้อมูลทุก {interval_hours} ชั่วโมง")
        
        # รันครั้งแรกทันที
        self.run_once()
        
        # ตั้ง schedule
        schedule.every(interval_hours).hours.do(self.run_once)
        
        # Loop รัน schedule
        while True:
            schedule.run_pending()
            time.sleep(60)  # ตรวจสอบทุกนาที


# ============================================
# ตัวอย่างการใช้งาน
# ============================================

if __name__ == "__main__":
    # ตัวอย่าง config - แก้ไขตามเว็บที่ต้องการ
    config = {
        # URLs
        'login_url': 'https://example.com/login',      # URL หน้า login
        'data_url': 'https://example.com/dashboard',   # URL หน้าข้อมูล
        
        # Credentials
        'username': 'your_username',
        'password': 'your_password',
        
        # Field names (ดูจาก HTML form)
        'username_field': 'username',  # หรือ 'email', 'user', etc.
        'password_field': 'password',  # หรือ 'pass', 'pwd', etc.
        
        # CSS Selectors สำหรับดึงข้อมูลเฉพาะ (optional)
        'selectors': {
            'title': 'h1.page-title',
            'stats': '.stat-value',
            'items': '.item-list li',
        },
        
        # Output settings
        'output_dir': 'data',
        'output_format': 'json',  # 'json' หรือ 'csv'
        'save_raw_html': False,
    }
    
    # สร้าง scraper
    scraper = WebScraper(config)
    
    # เลือกโหมดการทำงาน:
    
    # โหมด 1: รันครั้งเดียว (สำหรับทดสอบ)
    # scraper.run_once()
    
    # โหมด 2: รันทุกชั่วโมง
    scraper.run_scheduled(interval_hours=1)