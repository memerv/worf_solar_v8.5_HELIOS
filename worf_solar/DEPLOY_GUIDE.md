# คู่มือ Deploy จาก VS Code ขึ้น GitHub แล้วปล่อยเป็นลิงก์ (Streamlit Community Cloud)

สถานการณ์: สร้าง repo เปล่าไว้แล้วที่ `github.com/memerv/worf_solar_v8_HELIOS`
และเปิดโฟลเดอร์โค้ด `worf_solar` อยู่ใน VS Code

---

## ขั้นตอนที่ 1 — เปิด Terminal ใน VS Code

`Terminal` (เมนูบนสุด) → `New Terminal`
ต้องแน่ใจว่า terminal อยู่ **ที่โฟลเดอร์ `worf_solar`** (โฟลเดอร์ที่มี `app.py`)
เช็กง่ายๆ พิมพ์:

```bash
ls
```

ต้องเห็น `app.py`, `requirements.txt`, `packages.py` ฯลฯ ถ้าไม่เห็นให้ `cd` เข้าโฟลเดอร์ให้ถูกก่อน

---

## ขั้นตอนที่ 2 — เช็กไฟล์อ่อนไหวก่อน push (สำคัญมาก)

ห้ามให้รหัสผ่านจริงหลุดขึ้น GitHub เด็ดขาด (โดยเฉพาะถ้าตั้ง repo เป็น Public)
เช็กว่ามีไฟล์นี้อยู่ไหม แล้ว **ต้องไม่ถูก track โดย git**:

```bash
cat .gitignore
```

ต้องมีบรรทัด `.streamlit/secrets.toml` อยู่ในนั้น (ไฟล์นี้เตรียมไว้ให้แล้วในซิป)
ถ้ามีไฟล์ `.streamlit/secrets.toml` ที่ใส่รหัสจริงอยู่แล้ว **อย่าเอาขึ้น GitHub** —
ให้ตั้งรหัสผ่านผ่านหน้าเว็บ Streamlit Cloud แทนตอน deploy (ขั้นตอนที่ 4)

---

## ขั้นตอนที่ 3 — Push ขึ้น GitHub

รันทีละบรรทัดใน terminal (คัดลอก URL จากหน้า GitHub ของตัวเองด้วย — ในเคสนี้คือ URL ที่เห็นในรูป):

```bash
git init
git add .
git commit -m "worf solar v8 helios"
git branch -M main
git remote add origin https://github.com/memerv/worf_solar_v8_HELIOS.git
git push -u origin main
```

### ถ้าเจอ error ตอน push (พบบ่อยที่สุด)

**"remote origin already exists"** → แปลว่าเคยรัน `git remote add origin` ไปแล้ว แก้ด้วย:
```bash
git remote set-url origin https://github.com/memerv/worf_solar_v8_HELIOS.git
git push -u origin main
```

**ขึ้นหน้าต่างให้ล็อกอิน GitHub** → กด "Sign in with your browser" ตามที่ VS Code เด้งขึ้นมา
ล็อกอินในเบราว์เซอร์ครั้งเดียว ครั้งต่อไป push ได้เลยไม่ต้องล็อกอินซ้ำ

**"Support for password authentication was removed"** → GitHub ไม่รับรหัสผ่านบัญชีตรงๆ แล้ว
ต้องใช้ **Personal Access Token** แทนรหัสผ่าน หรือง่ายสุดคือใช้ปุ่ม
**Source Control** (ไอคอนกิ่งก้านซ้ายมือของ VS Code) → กด "Publish Branch" / "Sync Changes"
แล้วให้ VS Code จัดการล็อกอินให้อัตโนมัติแทนการพิมพ์คำสั่งเอง

**push แล้วรอนาน/ค้าง** → เช็กว่าไฟล์ในซิปไม่มี `__pycache__/` หรือไฟล์ข้อมูลลูกค้าจริงติดไปด้วย
(ไฟล์เทมเพลต Excel ตัวอย่างที่ผมสร้างให้ไม่มีปัญหา แต่ถ้าคุณเพิ่มไฟล์บิลลูกค้าจริงลงโฟลเดอร์นี้ อย่า push ขึ้น public repo)

---

## ขั้นตอนที่ 4 — Deploy บน Streamlit Community Cloud

1. ไปที่ **share.streamlit.io** ล็อกอินด้วยบัญชี GitHub เดียวกัน (memerv)
2. กด **"Create app"**
3. เลือก repository: `memerv/worf_solar_v8_HELIOS` · branch: `main` · main file path: `app.py`
4. ก่อนกด Deploy ให้กด **"Advanced settings"** → แท็บ **Secrets** แล้ววาง:
   ```toml
   APP_PASSWORD = "ตั้งรหัสที่คาดเดายากจริงๆ"
   ```
   (นี่คือรหัสผ่านที่คนเข้าเว็บต้องกรอกก่อนใช้แอป — ตั้งเองตรงนี้ ไม่ใช่ค่าที่มากับโค้ด)
5. กด **Deploy** รอ 2-5 นาที ระบบจะติดตั้ง package ตาม `requirements.txt` ให้เอง
6. เสร็จแล้วจะได้ลิงก์รูปแบบ `https://xxxxx.streamlit.app` — เข้า **App settings** เพื่อ
   เปลี่ยนเป็นชื่อที่จำง่าย เช่น `worf-solar.streamlit.app`

---

## ขั้นตอนที่ 5 — อัปเดตแอปในอนาคต

แก้โค้ดใน VS Code เสร็จแล้วแค่:
```bash
git add .
git commit -m "อธิบายว่าแก้อะไร"
git push
```
แอปบน Streamlit Cloud จะรีสตาร์ทและอัปเดตให้อัตโนมัติภายในไม่กี่นาที ไม่ต้อง deploy ใหม่

---

## เช็กลิสต์ก่อนส่งลิงก์ให้คนอื่น

- [ ] ตั้ง `APP_PASSWORD` ใน Secrets ของ Streamlit Cloud แล้ว (ไม่ใช่ค่า default)
- [ ] ทดสอบเข้าลิงก์เอง 1 รอบ ลองอัปโหลดไฟล์ตัวอย่างดูว่าคำนวณได้
- [ ] ถ้า repo เป็น Public: เช็กว่าไม่มีไฟล์บิล/ข้อมูลลูกค้าจริงติดไปใน repo
- [ ] แจกลิงก์ + รหัสผ่านให้เฉพาะทีมที่ควรเข้าถึง
