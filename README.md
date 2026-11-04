# Take-home-iot

ระบบ IoT ควบคุม/อ่านค่าผ่าน AI Chat box (โจทย์: `reference/problem/IoT AI Chat Control Architecture.png`)

```
                 MCP (HTTP)                      GPIO
AI Chat box ───────────────────▶ Raspberry Pi ──GPIO/I2C─▶ SHT3x / HC-SR04 / LED
 (Claude)                            │  ▲
                                     │  │ MQTT 1883
                                     ▼  │
LoRa node ──LoRa──▶ ChirpStack ──▶ MQTT broker lora.kmitl.ac.th ──WSS 8884──▶ Web Dashboard
(UNO R4 + LDR)                     (Pi topics + LoRa uplinks)
```

| Folder | คืออะไร |
| --- | --- |
| `arduino-lora/` | LoRa node: Arduino UNO R4 + Cytron LoRa RFM 915MHz shield + MH Light sensor (LDR) |
| `raspberry-pi/` | MCP server + REST API + MQTT client บน Raspberry Pi |
| `dashboard/` | เว็บ HTML/JS subscribe MQTT ผ่าน WebSocket แสดงค่า Pi + LoRa และสั่ง LED |
| `client-mcp/` | ตั้งค่า Claude Code เป็น AI Chat box ต่อกับ MCP server บน Pi (ดู `client-mcp/README.md`) |
| `reference/` | ไฟล์อ้างอิงจากโจทย์ |

ทุกส่วนใช้ MQTT broker เดียวกัน: `lora.kmitl.ac.th` (TCP `1883`, WebSocket `wss://lora.kmitl.ac.th:8884/mqtt`, ไม่มี auth)

ลำดับการทำ: **1. ต่อสาย → 2. Arduino → 3. ChirpStack → 4. Raspberry Pi → 5. Dashboard → 6. เชื่อม AI**

---

## 1. ต่อสาย

### Raspberry Pi

เลข GPIO เป็น BCM ส่วน "Pin" คือขาจริงบน header 40 ขา

| อุปกรณ์ | ขาอุปกรณ์ | GPIO | Pin |
| --- | --- | --- | --- |
| SHT3x | VCC | 3.3V | 1 |
| SHT3x | SDA (DATA) | GPIO 2 (SDA1) | 3 |
| SHT3x | SCL (SCK) | GPIO 3 (SCL1) | 5 |
| SHT3x | GND | GND | 9 |
| HC-SR04 | VCC | 5V | 2 |
| HC-SR04 | Trig | GPIO 14 | 8 |
| HC-SR04 | Echo | GPIO 15 | 10 (ผ่าน voltage divider ด้านล่าง) |
| HC-SR04 | GND | GND | 6 |
| LED | ขายาว (+) | GPIO 23 | 16 (ผ่าน R 220-330 Ω) |
| LED | ขาสั้น (−) | GND | 14 |

- **HC-SR04 Echo ออก 5V แต่ GPIO ของ Pi รับได้ 3.3V** ต้องแบ่งแรงดันก่อน:
  `Echo ── 1kΩ ──┬── GPIO 15`
  `              └── 2kΩ ── GND`
- **เซนเซอร์อุณหภูมิ/ความชื้นเป็น SHT3x แบบ I2C (address 0x44)** แม้โมดูลบอร์ดเขียวจะถูกเรียกว่า SHT15
  (ตรวจแล้วด้วย `i2cdetect -y 1` เจอ 0x44 และตอบคำสั่ง SHT3x) ต้องเปิด I2C ตามหัวข้อ "ตั้งค่า Pi"
- ใช้ไฟ 3.3V เท่านั้น (ห้ามต่อ 5V เพราะ SDA/SCL ต่อตรงเข้า Pi) โมดูลมี connector 5 ขา
  ให้ดูชื่อขาที่พิมพ์บนบอร์ด ขาที่เหลือไม่ต้องต่อ
- GPIO 2/3 บน Pi มี pull-up 1.8kΩ ในบอร์ดอยู่แล้ว ไม่ต้องใส่ pull-up เพิ่ม
- เช็กเซนเซอร์ (หยุด main.py ก่อน): `cd raspberry-pi && python -m tools.sht3x_check`

### LoRa node (Arduino)

1. เสียบ Cytron LoRa RFM 915MHz shield บน UNO R4 และต่อเสาอากาศก่อนเปิดไฟทุกครั้ง
2. ต่อ MH Light sensor (LDR) เข้ากับ shield:

| MH Light sensor | Arduino |
| --- | --- |
| VCC | 5V |
| GND | GND |
| AO | A0 |
| DO | D0 |

---

## 2. Arduino LoRa node

อ่าน LDR แล้วส่ง uplink ขึ้น ChirpStack ทุก 60 วินาที (OTAA, AS923)
Payload 3 bytes: `[light_raw_hi, light_raw_lo, light_digital]`
- `light_raw` = `analogRead(A0)` 0-1023
- `light_digital` = `digitalRead(D0)` 0/1 (threshold ปรับได้ที่ตัว R ปรับค่าบนโมดูล)

ขั้นตอน:

1. Arduino IDE → Boards Manager ติดตั้ง **Arduino UNO R4 Boards**
2. Library Manager ติดตั้ง **MCCI LoRaWAN LMIC library**
3. แก้ `Documents/Arduino/libraries/MCCI_LoRaWAN_LMIC_library/project_config/lmic_project_config.h` ให้เหลือ:
   ```c
   #define CFG_as923 1
   #define CFG_sx1276_radio 1
   ```
4. สร้างไฟล์ key:
   ```bash
   cp arduino-lora/LoRa_Node/secrets.example.h arduino-lora/LoRa_Node/secrets.h
   ```
   ใส่ค่าจาก `reference/lora-uno-r4/chirpstack.txt`
   - `APPEUI`, `DEVEUI` → **กลับลำดับ byte** (ChirpStack แสดง MSB แต่ LMIC ต้องการ LSB)
   - `APPKEY` → ใส่ตามเดิม
   (`secrets.h` อยู่ใน `.gitignore` จะไม่ถูก commit)
5. เปิด `arduino-lora/LoRa_Node/LoRa_Node.ino` เลือก board **Arduino UNO R4 WiFi** (หรือ Minima) และ port แล้ว Upload
6. เปิด Serial Monitor ที่ **9600** baud ควรเห็น:
   ```
   EV_JOINING
   EV_JOINED
   light_raw=512 light_digital=1
   Packet queued
   EV_TXCOMPLETE (includes waiting for RX windows)
   ```
   ถ้าค้างที่ `EV_JOINING` / `EV_JOIN_TXCOMPLETE: no JoinAccept` ให้เช็ก key, ลำดับ byte, เสาอากาศ และว่าอยู่ในระยะ gateway

## 3. ChirpStack

1. (แนะนำ) Device profile → Codec → JavaScript ใส่ `arduino-lora/chirpstack-codec.js`
   เพื่อให้ uplink มี field `object: {light_raw, light_digital}` (ถ้าไม่ใส่ Pi กับ dashboard จะ decode จาก `data` เอง)
2. จด **application_id** (UUID ในหน้า Application) เพื่อใช้ใน Pi และ dashboard
3. เช็กว่าข้อมูลขึ้น MQTT แล้ว:
   ```bash
   mosquitto_sub -h lora.kmitl.ac.th -p 1883 -v \
     -t "application/<application_id>/device/0a1930bd3503d95c/event/up"
   ```

## 4. Raspberry Pi

Server เดียว port 8000:

- `/mcp` — MCP server (Streamable HTTP) สำหรับ AI Chat box
- `/api/*` — REST API
- `/` — หน้า dashboard

### ตั้งค่า Pi (ทำครั้งเดียว)

```bash
sudo raspi-config
```

- Interface Options → **Serial Port** → login shell: **No**, serial hardware: **No** (GPIO 14/15 เป็น UART)
- Interface Options → **I2C** → **Yes** (SHT3x ใช้ I2C บน GPIO 2/3) หรือ `sudo raspi-config nonint do_i2c 0`
- Reboot

### ติดตั้ง

```bash
# ต้องเป็น Raspberry Pi OS 64-bit (Bookworm ขึ้นไป, Python 3.10+)
sudo apt update
sudo apt install -y git python3-venv python3-rpi-lgpio mosquitto-clients

git clone git@github.com:Makufff/Take-home-iot.git
cd Take-home-iot/raspberry-pi
# --system-site-packages เพื่อใช้ GPIO library (rpi-lgpio) ที่ติดตั้งจาก apt
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

ใน `.env` ต้องแก้:

| ค่า | ใส่อะไร |
| --- | --- |
| `TOPIC_PREFIX` | `67070067` (ตั้งไว้แล้ว ต้องตรงกับช่อง Topic prefix ใน dashboard) |
| `LORA_APPLICATION_ID` | application_id จาก ChirpStack |
| `LORA_DEV_EUI` | DevEUI ตัวเล็ก (ตั้งไว้แล้ว `0a1930bd3503d95c`) |

### รัน

```bash
source .venv/bin/activate
python main.py
```

ควรเห็น:

```
[mqtt] lora.kmitl.ac.th connected: Success
INFO:     Uvicorn running on http://0.0.0.0:8000
```

ทดสอบ:

```bash
curl http://localhost:8000/api/status
mosquitto_sub -h lora.kmitl.ac.th -v -t "67070067/#"
mosquitto_pub -h lora.kmitl.ac.th -t "67070067/pi/device/led/set" -m on
```

ทดสอบบนเครื่องที่ไม่มี GPIO (เช่น laptop): `SIMULATE=1 python main.py` (ค่าเซนเซอร์สุ่ม)

### รันอัตโนมัติตอนเปิดเครื่อง (ไม่บังคับ)

`/etc/systemd/system/pi-iot.service` (แก้ path/user ให้ตรง):

```ini
[Unit]
Description=Pi IoT MCP server
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/Take-home-iot/raspberry-pi
ExecStart=/home/pi/Take-home-iot/raspberry-pi/.venv/bin/python main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pi-iot
journalctl -u pi-iot -f
```

### MQTT topics (นำหน้าด้วย `67070067/`)

| Topic | ทิศทาง | Payload |
| --- | --- | --- |
| `pi/sensor/temperature` | Pi → broker (retain) | `26.5` |
| `pi/sensor/humidity` | Pi → broker (retain) | `62.0` |
| `pi/sensor/distance` | Pi → broker (retain) | `120.3` |
| `pi/device/led` | Pi → broker (retain) | `on` / `off` |
| `pi/device/led/set` | ใครก็ได้ → Pi | `on` / `off` |
| `pi/status` | Pi → broker (LWT, retain) | `online` / `offline` |
| `lora/node1/data` | Pi → broker (retain) | JSON ค่าล่าสุดของ LoRa node |

LoRa uplink จาก ChirpStack: `application/{application_id}/device/{dev_eui}/event/up` (ไม่มี prefix)

### MCP tools

| Tool | ทำอะไร |
| --- | --- |
| `read_pi_sensors` | อ่านอุณหภูมิ/ความชื้น (SHT3x) และระยะทาง (HC-SR04) |
| `control_pi_led` | เปิด/ปิด LED บน Pi |
| `read_lora_node` | ค่าล่าสุดจาก LoRa node (แสง, RSSI, SNR) |
| `list_mqtt_topics` | รายชื่อ topic ที่มีข้อความ |
| `read_mqtt` | อ่านข้อความล่าสุดของ topic |
| `publish_mqtt` | ส่งข้อความไปยัง MQTT broker |

### REST API

| Method | Path | |
| --- | --- | --- |
| GET | `/api/status` | ค่าล่าสุดทั้งหมด (Pi, LoRa, สถานะ MQTT) |
| GET | `/api/history?minutes=15` | ประวัติค่าเซนเซอร์ Pi |
| POST | `/api/pi/sensors/read` | อ่านเซนเซอร์ทันที |
| POST | `/api/pi/led` | `{"on": true}` |

## 5. Dashboard

Dashboard ต่อ MQTT ผ่าน WebSocket (`wss://lora.kmitl.ac.th:8884/mqtt`) โดยตรง ไม่ต้องผ่าน Pi

เปิดได้ 2 แบบ:

- ผ่าน Pi: `http://<ip-ของ-pi>:8000/`
- เปิดไฟล์ตรงบนเครื่องไหนก็ได้: ดับเบิลคลิก `dashboard/index.html` หรือ
  ```bash
  cd dashboard && python3 -m http.server 8080   # แล้วเปิด http://localhost:8080
  ```

ครั้งแรกจะเปิดช่อง **MQTT settings** ให้กรอก:

- **Topic prefix** = `67070067` (ตั้งไว้ให้แล้ว ต้องตรงกับ `TOPIC_PREFIX` ใน `.env` ของ Pi)
- **ChirpStack application_id**
- กด **Save & reconnect** (ค่าจะถูกจำไว้ใน browser)

จุดสถานะมุมขวาบน: **MQTT** = ต่อ broker ได้, **Pi** = Pi online (`pi/status`), **LoRa** = ได้ uplink แล้ว
(LoRa ส่งทุก 60 วินาที ต้องรอ uplink แรกก่อน)

## 6. เชื่อม AI Chat box (Claude)

วิธีที่ง่ายที่สุด: `cd client-mcp && claude` (ดู `client-mcp/README.md`) หรือตั้งค่าเองตามด้านล่าง

เครื่องที่รัน Claude ต้องอยู่ในเครือข่ายเดียวกับ Pi (เปลี่ยน `raspberrypi.local` เป็น IP ของ Pi ถ้าหาชื่อไม่เจอ)

**Claude Code**

```bash
claude mcp add --transport http pi-iot http://raspberrypi.local:8000/mcp
```

**Claude Desktop** (Settings → Developer → Edit Config → `claude_desktop_config.json`, ต้องมี Node.js):

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

แล้วรีสตาร์ท Claude Desktop ลองถาม:

- "เปิดไฟห้องเรียน"
- "อุณหภูมิตอนนี้เท่าไหร่"
- "ค่าแสงจาก LoRa node"
- "ระยะทางจาก ultrasonic เท่าไหร่"
