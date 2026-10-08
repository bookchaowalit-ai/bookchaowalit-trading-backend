---
title: Trading Bots Backend — Product Card
doc_id: CARD-bookchaowalit-trading-backend
doc_type: product-card
verdict: merge
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Trading Bots Backend — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

ชุดบอทเทรด Python หลาย exchange (Binance, Binance TH, Bitkub, InnovestX) ที่บังคับ paper mode เว้นแต่ตั้ง `TRADING_MODE=live` ตรงตัว

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ปัญหา: รันกลยุทธ์ grid/momentum/หุ้นไทยบนหลาย exchange โดยไม่เสี่ยงยิงคำสั่งจริงโดยไม่ตั้งใจ
- ผู้ใช้เป้าหมาย: เจ้าของ (ใช้คู่กับ `booktrading`) ไม่มีผู้ใช้ภายนอก **[ต้องยืนยัน]**

## 3. สิ่งที่ทำได้จริงตอนนี้

- `trading-bots/main.py` + `src/bot_manager.py` โหลด `bot_configs.json` และ start/stop บอทหลายตัว
- connector ใน `src/exchanges/`: binance, binance_th, bitkub, innovestx และ `paper_exchange.py` ที่ห่อทุก connector เมื่อไม่ใช่ live
- กลยุทธ์ใน `src/strategies/`: grid, momentum, thai_stock
- test offline 13 ไฟล์ (fee/cost basis, OHLCV, UTC timestamp, ค่า non-finite, paper exchange) รันใน CI
- สคริปต์ตั้งฐานข้อมูล (`setup_database.py`, `setup_database_neon.py`)

## 4. หลักฐานสถานะ

- Stack: Python (ccxt, pandas, psycopg2, loguru), pytest, ruff
- Commits: 18 (แรก 2025-10-17 / ล่าสุด 2026-10-01), branch `main`
- Source: 33 ไฟล์ / 5864 บรรทัด; test files: 13
- CI workflows: 1; deploy config: ไม่มี
- Live URL: ไม่มี
- README: 61 บรรทัด ("bookchaowalit-trading-backend"); template family size: 1

## 5. คุณค่าและจุดต่าง

- ค่าเริ่มต้นปลอดภัย (paper) และ test ที่จับบั๊กการเงินจริงจัง (fee, net fill)
- มี connector InnovestX และกลยุทธ์หุ้นไทยที่ไม่พบใน `booktrading`
- **[สมมติฐาน]** ไม่มีมุมรายได้แยก; คุณค่าเป็นส่วนประกอบของ BookFinance

## 6. ช่องว่างสำคัญ

- README ยอมรับเองว่าไม่ใช่ผลิตภัณฑ์เต็ม และเป็นพี่น้องของ `booktrading`
- grid trading และ Binance TH/Bitkub ทับซ้อนกับ `booktrading/strategy/app/`
- ไม่มี deploy config และการย้าย org ถูกเลื่อน (BD-034)

## 7. คำตัดสิน

**merge** → canonical: `bookchaowalit-ai/booktrading` ความสามารถซ้ำกันเป็นส่วนใหญ่; ส่วนที่ไม่ซ้ำ (InnovestX, กลยุทธ์หุ้นไทย, test ของ fee/fill) ควรย้ายเข้า canonical เงื่อนไขที่จะเปลี่ยนคำตัดสิน: ตัดสินใจแยกตลาดหุ้นไทยเป็นผลิตภัณฑ์ของตัวเอง

## 8. ขั้นต่อไป

1. เทียบ connector/test กับ `booktrading/strategy` แล้ว port ส่วนที่ไม่ซ้ำ
2. archive repo นี้หลังย้ายเสร็จและอนุมัติ

## การอนุมัติ

| บทบาท | การตัดสินใจ | วันที่ |
|---|---|---|
| Product owner (Book Dev) | [ต้องยืนยัน] verdict `merge` | — |

## แหล่งข้อมูล

- `bookchaowalit-ai/book-ai/bookchaowalit-trading-backend/README.md`
- `bookchaowalit-ai/book-ai/bookchaowalit-trading-backend/trading-bots/main.py`
- `bookchaowalit-ai/book-ai/bookchaowalit-trading-backend/trading-bots/src/bot_manager.py`
- `bookchaowalit-ai/book-ai/bookchaowalit-trading-backend/trading-bots/src/exchanges/`
- `bookchaowalit-ai/book-ai/bookchaowalit-trading-backend/trading-bots/tests/`
