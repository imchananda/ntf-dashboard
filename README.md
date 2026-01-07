# Web Scraper - ระบบดึงข้อมูลจากเว็บที่ต้อง Login

ระบบดึงข้อมูลอัตโนมัติจากเว็บไซต์ที่ต้องเข้าสู่ระบบ รองรับการทำงานแบบ schedule ทุกชั่วโมง

## คุณสมบัติ

- ✅ Login อัตโนมัติด้วย session/cookies
- ✅ รองรับ CSRF token
- ✅ Re-login อัตโนมัติเมื่อ session หมดอายุ
- ✅ ดึงข้อมูลจากตาราง HTML
- ✅ บันทึกเป็น JSON หรือ CSV
- ✅ ตั้ง schedule ดึงข้อมูลทุก X ชั่วโมง
- ✅ Logging ครบถ้วน

## ติดตั้ง

```bash
pip install -r requirements.txt
```

## การใช้งาน

### 1. แก้ไข config.json

```json
{
    "login_url": "https://your-website.com/login",
    "data_url": "https://your-website.com/data-page",
    "username": "your_username",
    "password": "your_password",
    "username_field": "username",
    "password_field": "password"
}
```

### 2. หา field names จาก HTML

เปิดหน้า login แล้วดู source code:

```html
<form action="/login" method="POST">
    <input name="email" type="text">      <!-- username_field = "email" -->
    <input name="pass" type="password">   <!-- password_field = "pass" -->
</form>
```

### 3. รันโปรแกรม

```bash
# รันครั้งเดียว (ทดสอบ)
python run.py --once

# รันทุก 1 ชั่วโมง
python run.py

# รันทุก 2 ชั่วโมง
python run.py --interval 2

# ใช้ config file อื่น
python run.py --config my_config.json
```

## โครงสร้างไฟล์

```
web_scraper/
├── scraper.py      # คลาสหลัก
├── run.py          # script สำหรับรัน
├── config.json     # ไฟล์ config
├── requirements.txt
├── scraper.log     # log file (สร้างอัตโนมัติ)
└── data/           # โฟลเดอร์เก็บข้อมูล
    ├── data_20250106_100000.json
    └── data_20250106_110000.json
```

## การดึงข้อมูลเฉพาะด้วย CSS Selectors

```json
{
    "selectors": {
        "page_title": "h1.title",
        "total_count": ".stat-box .count",
        "table_rows": "table.data tbody tr"
    }
}
```

## รันเป็น Background Service (Linux)

### ใช้ nohup

```bash
nohup python run.py > output.log 2>&1 &
```

### ใช้ systemd

สร้างไฟล์ `/etc/systemd/system/web-scraper.service`:

```ini
[Unit]
Description=Web Scraper Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/web_scraper
ExecStart=/usr/bin/python3 run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable web-scraper
sudo systemctl start web-scraper
```

## หมายเหตุ

- ตรวจสอบ Terms of Service ของเว็บก่อนใช้งาน
- ไม่ควรดึงข้อมูลถี่เกินไป อาจโดน block
- เก็บรหัสผ่านใน environment variable แทน config file ในระบบ production
