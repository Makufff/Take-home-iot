# Take-home-iot

ระบบ IoT ควบคุม/อ่านค่าผ่าน AI Chat box (โจทย์: `reference/problem/IoT AI Chat Control Architecture.png`)

```
AI Chat box (Claude) ──MCP (HTTP)──▶ Raspberry Pi ──GPIO──▶ SHT15 / HC-SR04 / LED
                                       │  ▲
                              REST API │  │ MQTT pub/sub
                                       ▼  │
                               Web Dashboard   HiveMQ (mqtt-dashboard.com)
                                          ▲
                                          │ MQTT (Pi bridge)
LoRa node (UNO R4 + LDR) ──LoRa──▶ ChirpStack ──MQTT──▶ lora.kmitl.ac.th
```

| Folder | คืออะไร |
| --- | --- |
| `arduino-lora/` | LoRa node: Arduino UNO R4 + Cytron LoRa RFM 915MHz shield + MH Light sensor (LDR) |
| `raspberry-pi/` | MCP server + REST API + MQTT bridge บน Raspberry Pi |
| `dashboard/` | เว็บ HTML/JS แสดงค่าและสั่ง LED ผ่าน REST API ของ Pi |
| `reference/` | ไฟล์อ้างอิงจากโจทย์ |

## 1. arduino-lora

อ่าน MH Light sensor แล้วส่ง uplink ผ่าน ChirpStack ขึ้น MQTT `lora.kmitl.ac.th` ทุก 60 วินาที

- A0 = ค่า analog (`light_raw` 0-1023), D0 = ค่า digital threshold (`light_digital`)
- Payload 3 bytes: `[light_raw_hi, light_raw_lo, light_digital]`

ติดตั้ง:

1. Library: **MCCI LoRaWAN LMIC library** ตั้งค่า region ใน `project_config/lmic_project_config.h` เป็น `CFG_as923` และ `CFG_sx1276_radio`
2. `cp arduino-lora/LoRa_Node/secrets.example.h arduino-lora/LoRa_Node/secrets.h` แล้วใส่ key จาก ChirpStack
   (APPEUI/DEVEUI ต้องกลับลำดับ byte เป็น LSB, APPKEY ใส่ตามเดิม) — `secrets.h` ไม่ถูก commit
3. Upload `arduino-lora/LoRa_Node/LoRa_Node.ino` (board: Arduino UNO R4)
4. (แนะนำ) ใส่ codec `arduino-lora/chirpstack-codec.js` ใน Device profile ของ ChirpStack เพื่อให้ uplink มี field `object`
   ถ้าไม่ใส่ Pi จะ decode จาก `data` เอง

## 2. raspberry-pi

Server เดียว (port 8000):

- `/mcp` — MCP server (Streamable HTTP) สำหรับ AI Chat box
- `/api/*` — REST API สำหรับ dashboard
- `/` — เสิร์ฟหน้า `dashboard/`

### ต่อสาย (BCM)

| อุปกรณ์ | GPIO |
| --- | --- |
| HC-SR04 Trigger | 14 |
| HC-SR04 Echo | 15 (Echo เป็น 5V ต้องใช้ voltage divider ลงเหลือ 3.3V) |
| LED | 23 |
| SHT15 DATA | 2 |
| SHT15 SCK | 3 |

ตั้งค่า Pi ก่อน (`sudo raspi-config` → Interface Options):

- **Serial Port: ปิด** login shell และ hardware serial เพราะ GPIO 14/15 คือ UART
- **I2C: ปิด** เพราะ SHT15 ไม่ใช่ I2C (ใช้ bit-bang protocol ของ Sensirion บน GPIO 2/3)

### ติดตั้งและรัน

```bash
cd raspberry-pi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ใส่ LORA_APPLICATION_ID, LORA_MQTT_USER/PASS, เปลี่ยน TOPIC_PREFIX
python main.py
```

ทดสอบบนเครื่องที่ไม่มี GPIO: `SIMULATE=1 python main.py` (ค่าเซนเซอร์สุ่ม)

### MCP tools

| Tool | ทำอะไร |
| --- | --- |
| `read_pi_sensors` | อ่านอุณหภูมิ/ความชื้น (SHT15) และระยะทาง (HC-SR04) |
| `control_pi_led` | เปิด/ปิด LED บน Pi |
| `read_lora_node` | ค่าล่าสุดจาก LoRa node (แสง, RSSI, SNR) |
| `list_mqtt_topics` | รายชื่อ topic ที่มีข้อความ |
| `read_mqtt` | อ่านข้อความล่าสุดของ topic |
| `publish_mqtt` | ส่งข้อความไปยัง MQTT broker |

เชื่อม Claude (เปลี่ยน `raspberrypi.local` เป็น IP ของ Pi):

```bash
# Claude Code
claude mcp add --transport http pi-iot http://raspberrypi.local:8000/mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pi-iot": {
      "command": "npx",
      "args": ["mcp-remote", "http://raspberrypi.local:8000/mcp", "--allow-http"]
    }
  }
}
```

### MQTT topics (HiveMQ, นำหน้าด้วย `TOPIC_PREFIX`)

| Topic | ทิศทาง | Payload |
| --- | --- | --- |
| `pi/sensor/temperature` | Pi → broker (retain) | `26.5` |
| `pi/sensor/humidity` | Pi → broker (retain) | `62.0` |
| `pi/sensor/distance` | Pi → broker (retain) | `120.3` |
| `pi/device/led` | Pi → broker (retain) | `on` / `off` |
| `pi/device/led/set` | broker → Pi | `on` / `off` |
| `pi/status` | Pi → broker (LWT) | `online` / `offline` |
| `lora/node1/data` | Pi → broker (retain) | JSON จาก LoRa node |

Pi subscribe `application/{LORA_APPLICATION_ID}/device/{LORA_DEV_EUI}/event/up` ที่ `lora.kmitl.ac.th`
แล้ว publish ต่อไปที่ `lora/node1/data`

### REST API

| Method | Path | |
| --- | --- | --- |
| GET | `/api/status` | ค่าล่าสุดทั้งหมด (Pi, LoRa, สถานะ MQTT) |
| GET | `/api/history?minutes=15` | ประวัติค่าเซนเซอร์ Pi |
| POST | `/api/pi/sensors/read` | อ่านเซนเซอร์ทันที |
| POST | `/api/pi/led` | `{"on": true}` |

## 3. dashboard

เปิด `http://raspberrypi.local:8000/` (Pi เสิร์ฟให้เอง)
หรือเปิด `dashboard/index.html` จากที่อื่นแล้วระบุ API: `index.html?api=http://raspberrypi.local:8000`
