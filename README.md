# FleetAI

แพลตฟอร์มจัดการเลขไมล์ ค่าใช้จ่าย เอกสารรถ และการเชื่อมต่อ LINE Bot โดยแยก backend (FastAPI) กับ frontend (HTML/Vanilla JS/CSS) เป็นระบบเดียวกันสำหรับ Deploy บน Render

## สิ่งที่ทำงานแล้ว

- Login ด้วย JWT และสิทธิ์ `owner`, `admin`, `editor`, `viewer`
- รถยนต์/มอเตอร์ไซค์, เลขไมล์ และการป้องกันเลขไมล์ลดลง
- ค่าใช้จ่าย 14 หมวด, เอกสารรถและแจ้งเตือนเอกสารใกล้หมดอายุ
- รหัสผูก LINE แบบใช้ครั้งเดียวอายุ 10 นาที และ Webhook endpoint `/webhook/line`
- Static multi-page: `/login` และ `/dashboard` พร้อมปิด cache หน้าเว็บหลัก

## ใช้งานในเครื่อง

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
python create_user.py --company "บริษัทของฉัน" --name "ผู้ดูแล" --email admin@example.com --password "ChangeMe123!"
uvicorn app.main:app --reload
```

เปิด `http://localhost:8000/login`

## Deploy บน Supabase + Render

1. สร้าง Project ใน Supabase แล้วคัดลอก **Connection string URI** (ใช้ค่าที่มี `postgresql://`)
2. Push โฟลเดอร์นี้ขึ้น GitHub จากนั้นสร้าง **Web Service** บน Render โดยเลือกโฟลเดอร์ `backend`
3. ตั้งค่า Build Command: `pip install -r requirements.txt`
4. ตั้งค่า Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. ใส่ Environment Variables: `DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES=480`, `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `APP_BASE_URL`
6. หลัง Deploy ครั้งแรก เปิด Render Shell แล้วสร้าง Owner:

```bash
python create_user.py --company "ชื่อบริษัท" --name "ชื่อผู้ดูแล" --email admin@example.com --password "รหัสผ่านที่ปลอดภัย"
```

7. ใน LINE Developers กำหนด Webhook URL เป็น `https://<render-url>/webhook/line` และเปิด **Use webhook**; ใน Official Account Manager ตั้ง Response mode = **Bot**, Auto-reply = **Disabled**

## Migration

รุ่นเริ่มต้นใช้ `Base.metadata.create_all()` เพื่อบูตตารางได้ทันทีทั้ง SQLite และ Supabase. ก่อนใช้งานจริงหลายสภาพแวดล้อมให้เริ่ม Alembic ด้วย:

```bash
cd backend
alembic init migrations
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

จากนั้นให้ย้ายคำสั่ง `Base.metadata.create_all()` ออกจาก `app/main.py` เพื่อให้ Alembic เป็นผู้ดูแล schema เพียงแหล่งเดียว

## สิ่งที่ต้องต่อเพิ่มก่อนเปิด OCR จริง

Webhook วางเส้นทางสำหรับ LINE และการผูกรถแล้ว แต่การอ่านภาพ OCR ต้องเชื่อมผู้ให้บริการ OCR เช่น Google Cloud Vision / Azure AI Vision และตรวจสอบ `X-Line-Signature` ด้วย `LINE_CHANNEL_SECRET` ก่อนประมวลผล event ใน production.
