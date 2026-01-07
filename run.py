#!/usr/bin/env python3
"""
Script สำหรับรัน Web Scraper
อ่าน config จากไฟล์ config.json
"""

import json
import argparse
from pathlib import Path
from scraper import WebScraper


def load_config(config_path: str = 'config.json') -> dict:
    """โหลด config จากไฟล์ JSON"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    # ลบ comment field ออก
    config.pop('_comment', None)
    return config


def main():
    parser = argparse.ArgumentParser(description='Web Scraper - ดึงข้อมูลจากเว็บที่ต้อง login')
    parser.add_argument('-c', '--config', default='config.json', help='ไฟล์ config (default: config.json)')
    parser.add_argument('-o', '--once', action='store_true', help='รันครั้งเดียว (ไม่ loop)')
    parser.add_argument('-i', '--interval', type=int, default=1, help='ความถี่ในการดึงข้อมูล (ชั่วโมง)')
    
    args = parser.parse_args()
    
    # โหลด config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ ไม่พบไฟล์ config: {config_path}")
        print("กรุณาสร้างไฟล์ config.json หรือระบุ path ด้วย -c")
        return
    
    config = load_config(args.config)
    
    # สร้าง scraper
    scraper = WebScraper(config)
    
    if args.once:
        # รันครั้งเดียว
        print("🔄 กำลังดึงข้อมูล...")
        if scraper.run_once():
            print("✅ เสร็จสิ้น")
        else:
            print("❌ ไม่สำเร็จ - ดู log สำหรับรายละเอียด")
    else:
        # รันแบบ schedule
        interval = args.interval or config.get('interval_hours', 1)
        print(f"🚀 เริ่มระบบดึงข้อมูลทุก {interval} ชั่วโมง")
        print("กด Ctrl+C เพื่อหยุด")
        try:
            scraper.run_scheduled(interval_hours=interval)
        except KeyboardInterrupt:
            print("\n👋 หยุดการทำงาน")


if __name__ == "__main__":
    main()
