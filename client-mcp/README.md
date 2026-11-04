# client-mcp

ใช้ Claude Code เป็น AI Chat box ต่อกับ MCP server บน Raspberry Pi (`raspberry-pi/`)

| ไฟล์ | |
| --- | --- |
| `.mcp.json` | ตั้งค่า MCP server `pi-iot` (Claude Code โหลดอัตโนมัติเมื่อเปิดในโฟลเดอร์นี้) |
| `CLAUDE.md` | บอก Claude ว่าอุปกรณ์มีอะไร และคำสั่งไหนใช้ tool ไหน |
| `check_connection.py` | ทดสอบว่าต่อ Pi ได้ โดยไม่ต้องใช้ Claude |

## 1. ให้ Pi รันอยู่ก่อน

บน Pi: `cd raspberry-pi && source .venv/bin/activate && python main.py` (ดู README หลัก)

เครื่องที่รัน Claude Code ต้องอยู่ในเครือข่ายเดียวกับ Pi

## 2. หา address ของ Pi

ปกติใช้ `raspberrypi.local` ได้เลย ถ้าไม่ได้ ให้หา IP บน Pi ด้วย `hostname -I`

## 3. ทดสอบการเชื่อมต่อ (ไม่บังคับ)

```bash
cd client-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python check_connection.py                       # ใช้ raspberrypi.local
PI_HOST=192.168.1.50 python check_connection.py  # หรือระบุ IP
```

ควรเห็น:

```
Tools: read_pi_sensors, control_pi_led, read_lora_node, list_mqtt_topics, read_mqtt, publish_mqtt
read_pi_sensors: {"temperature": 26.5, ...}
```

## 4. เปิด Claude Code

```bash
cd client-mcp
claude                          # ใช้ raspberrypi.local:8000
PI_HOST=192.168.1.50 claude     # หรือระบุ IP ของ Pi
```

ครั้งแรก Claude Code จะถามว่าจะใช้ MCP server `pi-iot` จาก `.mcp.json` ไหม → เลือกอนุญาต
เช็กสถานะได้ด้วย `/mcp` ใน Claude Code (ต้องขึ้น `pi-iot ✔ connected`)

ลองพิมพ์:

- เปิดไฟห้องเรียน
- อุณหภูมิตอนนี้เท่าไหร่
- ค่าแสงจาก LoRa node
- ระยะทางจาก ultrasonic เท่าไหร่
- แสดงข้อมูลบนเว็บให้หน่อย

## ใช้จากโฟลเดอร์อื่น

ถ้าอยากให้ `pi-iot` ใช้ได้ทุกโปรเจกต์ (ไม่ต้อง `cd client-mcp`):

```bash
claude mcp add --transport http --scope user pi-iot http://raspberrypi.local:8000/mcp
```

## แก้ปัญหา

| อาการ | สาเหตุ / วิธีแก้ |
| --- | --- |
| `/mcp` ขึ้น failed | Pi ไม่ได้รัน `main.py`, IP ผิด, หรือคนละเครือข่าย ลอง `curl http://<pi>:8000/api/status` |
| `raspberrypi.local` หาไม่เจอ | ใช้ IP ตรง ๆ ผ่าน `PI_HOST=...` |
| ค่าเซนเซอร์เป็น `null` | ดู log บน Pi (`[hardware] ...`) เช็กการต่อสาย |
| LoRa `node: null` | ยังไม่มี uplink หรือยังไม่ได้ตั้ง `LORA_APPLICATION_ID` ใน `.env` ของ Pi |
