import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Run without real GPIO (for development on a laptop)
SIMULATE = _bool("SIMULATE")

# GPIO (BCM numbering) - reference/port-connect.txt
PIN_TRIGGER = 14
PIN_ECHO = 15
PIN_LED = 23
PIN_SHT15_DATA = 2
PIN_SHT15_SCK = 3

SAMPLE_INTERVAL = float(os.getenv("SAMPLE_INTERVAL", "5"))

# HTTP server (REST API + MCP + dashboard)
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
DASHBOARD_DIR = Path(os.getenv("DASHBOARD_DIR", BASE_DIR.parent / "dashboard"))

# MQTT broker (lora.kmitl.ac.th, no auth). The Pi topics and the ChirpStack
# uplinks of the LoRa node are on the same broker.
MQTT_HOST = os.getenv("MQTT_HOST", "lora.kmitl.ac.th")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_PREFIX = os.getenv("TOPIC_PREFIX", "67070067").strip("/")

# ChirpStack: uplink topic application/{LORA_APPLICATION_ID}/device/{LORA_DEV_EUI}/event/up
LORA_APPLICATION_ID = os.getenv("LORA_APPLICATION_ID", "")
LORA_DEV_EUI = os.getenv("LORA_DEV_EUI", "").lower()

# Rough raw -> lux for the MH light module (LDR to GND, fixed resistor to VCC, so
# a higher raw value means darker). Uncalibrated estimate: GL5528-type LDR is
# ~10-20 kOhm at 10 lux with gamma ~0.7. Tune these against a lux meter.
LDR_FIXED_OHMS = float(os.getenv("LDR_FIXED_OHMS", "10000"))
LDR_R10_OHMS = float(os.getenv("LDR_R10_OHMS", "15000"))
LDR_GAMMA = float(os.getenv("LDR_GAMMA", "0.7"))
