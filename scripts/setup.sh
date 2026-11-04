#!/usr/bin/env bash
# Interactive setup: asks for the values a part needs and writes its config file.
#   bash scripts/setup.sh [pi] [arduino] [mcp] [dashboard]     (no argument = all)
#   make setup | setup-pi | setup-arduino | setup-mcp | setup-dashboard
#
# Writes:
#   .env                                   answers (defaults for the next run, read by the Makefile)
#   pi        -> raspberry-pi/.env                  Pi server config
#   arduino   -> arduino-lora/LoRa_Node/secrets.h   OTAA keys (APPEUI/DEVEUI byte order reversed for LMIC)
#   mcp       -> client-mcp/.mcp.json               default Pi host/port
#   dashboard -> dashboard/app.js                   DEFAULTS (broker, prefix, appId, devEui)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/.env"
PI_ENV="$ROOT/raspberry-pi/.env"
SECRETS="$ROOT/arduino-lora/LoRa_Node/secrets.h"
APP_JS="$ROOT/dashboard/app.js"
MCP_JSON="$ROOT/client-mcp/.mcp.json"
CHIRPSTACK_TXT="$ROOT/reference/lora-uno-r4/chirpstack.txt"
LMIC_CONFIG="${LMIC_CONFIG:-$HOME/Documents/Arduino/libraries/MCCI_LoRaWAN_LMIC_library/project_config/lmic_project_config.h}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# ask VAR "question" "default"
ASKED=" "
ask() {
  local var="$1" question="$2" default="${3:-}" answer
  case "$ASKED" in *" $var "*) return ;; esac
  ASKED="$ASKED$var "
  if [ -n "$default" ]; then
    read -r -p "  $question [$default]: " answer || true
  else
    read -r -p "  $question: " answer || true
  fi
  printf -v "$var" '%s' "${answer:-$default}"
}

# ask_yn "question" "y|n" -> exit status 0 = yes
ask_yn() {
  local answer
  read -r -p "  $1 [$2]: " answer || true
  answer="$(printf '%s' "${answer:-$2}" | tr '[:upper:]' '[:lower:]')"
  [ "$answer" = "y" ] || [ "$answer" = "yes" ]
}

# Normalise "0x0A, 0x19 ..." / "0a:19:..." / "0A19..." to "0A19..."
hex_clean() {
  printf '%s' "$1" | sed -e 's/0[xX]//g' | tr -d ' ,:{}\t-' | tr '[:lower:]' '[:upper:]'
}

# ask_hex VAR "question" "default" bytes
ask_hex() {
  local var="$1" question="$2" default="$3" bytes="$4" value
  case "$ASKED" in *" $var "*) return ;; esac
  while true; do
    read -r -p "  $question${default:+ [$default]}: " value || true
    value="${value:-$default}"
    value="$(hex_clean "$value")"
    if printf '%s' "$value" | grep -Eq "^[0-9A-F]{$((bytes * 2))}\$"; then
      printf -v "$var" '%s' "$value"
      ASKED="$ASKED$var "
      return
    fi
    warn "ต้องเป็น hex $bytes bytes ($((bytes * 2)) ตัวอักษร) ลองใหม่"
  done
}

# "0A1930BD" -> "0x0A, 0x19, 0x30, 0xBD" (reverse=1 flips byte order)
c_bytes() {
  local hex="$1" reverse="${2:-0}" out="" byte i
  for ((i = 0; i < ${#hex}; i += 2)); do
    byte="0x${hex:i:2}"
    if [ "$reverse" = 1 ]; then out="$byte${out:+, }$out"; else out="$out${out:+, }$byte"; fi
  done
  printf '%s' "$out"
}

# Key from reference/lora-uno-r4/chirpstack.txt, e.g. "DEVEUI = 0x0A, ..."
chirpstack_key() {
  [ -f "$CHIRPSTACK_TXT" ] || return 0
  hex_clean "$(grep -E "^$1[[:space:]]*=" "$CHIRPSTACK_TXT" | head -1 | cut -d= -f2)"
}

# Replace a line in a file (portable: no sed -i)
sed_file() {
  local file="$1" expr="$2" tmp
  tmp="$(mktemp)"
  sed -e "$expr" "$file" >"$tmp" && cat "$tmp" >"$file"
  rm -f "$tmp"
}

# ---------------------------------------------------------------------------
# Defaults: previous answers (.env) > existing files > reference values
if [ -f "$STATE" ]; then
  # shellcheck disable=SC1090
  . "$STATE"
elif [ -f "$PI_ENV" ]; then
  # shellcheck disable=SC1090
  . "$PI_ENV"
fi
if [ -z "${LORA_APPLICATION_ID:-}" ] && [ -f "$APP_JS" ]; then
  LORA_APPLICATION_ID="$(sed -n 's/^  appId: "\(.*\)",$/\1/p' "$APP_JS")"
fi
: "${TOPIC_PREFIX:=67070067}"
: "${MQTT_HOST:=lora.kmitl.ac.th}"
: "${MQTT_PORT:=1883}"
: "${MQTT_WS_URL:=wss://lora.kmitl.ac.th:8884/mqtt}"
: "${SIMULATE:=0}"
: "${SAMPLE_INTERVAL:=5}"
: "${HTTP_PORT:=8000}"
: "${PI_HOST:=raspberrypi.local}"
: "${LORA_DEV_EUI:=$(chirpstack_key DEVEUI)}"
: "${LORA_APP_EUI:=$(chirpstack_key APPEUI)}"
: "${LORA_APP_KEY:=$(chirpstack_key APPKEY)}"

ask_topic() {
  ask TOPIC_PREFIX "Topic prefix (รหัสนักศึกษา)" "$TOPIC_PREFIX"
  TOPIC_PREFIX="${TOPIC_PREFIX%/}"
}

ask_lora_ids() {
  ask LORA_APPLICATION_ID "ChirpStack Application ID (UUID)" "${LORA_APPLICATION_ID:-}"
  ask_hex LORA_DEV_EUI "DevEUI (ตามที่ ChirpStack แสดง)" "${LORA_DEV_EUI:-}" 8
  [ -n "$LORA_APPLICATION_ID" ] || warn "ยังไม่ได้ใส่ Application ID: จะไม่เห็น uplink จาก LoRa"
  DEV_EUI_LOWER="$(printf '%s' "$LORA_DEV_EUI" | tr '[:upper:]' '[:lower:]')"
}

setup_pi() {
  echo
  bold "Raspberry Pi -> raspberry-pi/.env"
  ask_topic
  ask MQTT_HOST "MQTT host" "$MQTT_HOST"
  ask MQTT_PORT "MQTT TCP port" "$MQTT_PORT"
  ask_lora_ids
  ask HTTP_PORT "HTTP port ของ server บน Pi" "$HTTP_PORT"
  ask SAMPLE_INTERVAL "อ่านเซนเซอร์ทุกกี่วินาที" "$SAMPLE_INTERVAL"
  if ask_yn "SIMULATE (ค่าเซนเซอร์สุ่ม ไม่ใช้ GPIO)? y/n" "$([ "$SIMULATE" = 1 ] && echo y || echo n)"; then
    SIMULATE=1
  else
    SIMULATE=0
  fi

  cat >"$PI_ENV" <<EOF
# Generated by 'make setup-pi'. .env is git-ignored.

# 1 = fake sensor values, no GPIO (for testing on a laptop)
SIMULATE=$SIMULATE
SAMPLE_INTERVAL=$SAMPLE_INTERVAL

HTTP_HOST=0.0.0.0
HTTP_PORT=$HTTP_PORT

# MQTT broker (no auth). The broker is shared with other students,
# so TOPIC_PREFIX keeps our topics separate (student ID).
MQTT_HOST=$MQTT_HOST
MQTT_PORT=$MQTT_PORT
TOPIC_PREFIX=$TOPIC_PREFIX

# ChirpStack application ID (UUID from the ChirpStack console)
LORA_APPLICATION_ID=$LORA_APPLICATION_ID
# DevEUI lowercase hex, as in the ChirpStack topic
LORA_DEV_EUI=$DEV_EUI_LOWER
EOF
  info "raspberry-pi/.env"
  NEXT="$NEXT  Pi        : make pi-apt pi-install && make pi-run   (หรือ make pi-service)\n"
}

setup_arduino() {
  echo
  bold "Arduino LoRa node -> arduino-lora/LoRa_Node/secrets.h"
  echo "  ใส่ค่าตามที่ ChirpStack แสดง เช่น 0A1930BD3503D95C (สคริปต์กลับลำดับ byte ให้เอง)"
  ask_hex LORA_DEV_EUI "DevEUI" "${LORA_DEV_EUI:-}" 8
  ask_hex LORA_APP_EUI "JoinEUI / AppEUI" "${LORA_APP_EUI:-}" 8
  ask_hex LORA_APP_KEY "AppKey" "${LORA_APP_KEY:-}" 16

  cat >"$SECRETS" <<EOF
// Generated by 'make setup-arduino'. secrets.h is git-ignored.
#pragma once

// APPEUI (JoinEUI) and DEVEUI are LSB first (little endian):
// byte order reversed from the ChirpStack console.
// APPEUI shown in ChirpStack: $LORA_APP_EUI
// DEVEUI shown in ChirpStack: $LORA_DEV_EUI
static const u1_t PROGMEM APPEUI[8] = { $(c_bytes "$LORA_APP_EUI" 1) };
static const u1_t PROGMEM DEVEUI[8] = { $(c_bytes "$LORA_DEV_EUI" 1) };

// APPKEY is MSB first: copied as-is from the ChirpStack console.
static const u1_t PROGMEM APPKEY[16] = { $(c_bytes "${LORA_APP_KEY:0:16}"),
                                         $(c_bytes "${LORA_APP_KEY:16:16}") };
EOF
  info "arduino-lora/LoRa_Node/secrets.h"

  if [ -f "$LMIC_CONFIG" ]; then
    if grep -q '^#define CFG_as923 1' "$LMIC_CONFIG" && grep -q '^#define CFG_sx1276_radio 1' "$LMIC_CONFIG" \
      && [ "$(grep -c '^#define CFG_' "$LMIC_CONFIG")" = 2 ]; then
      info "LMIC config เป็น AS923 + SX1276 อยู่แล้ว"
    elif ask_yn "ตั้ง LMIC library เป็น AS923 + SX1276 ($LMIC_CONFIG)? y/n" "y"; then
      cp "$LMIC_CONFIG" "$LMIC_CONFIG.bak"
      printf '#define CFG_as923 1\n#define CFG_sx1276_radio 1\n' >"$LMIC_CONFIG"
      info "lmic_project_config.h (backup: .bak)"
    fi
  else
    warn "ไม่เจอ LMIC library ที่ $LMIC_CONFIG (ติดตั้ง MCCI LoRaWAN LMIC ใน Arduino IDE แล้วรันใหม่ หรือแก้เองตาม README)"
  fi
  NEXT="$NEXT  Arduino   : เปิด arduino-lora/LoRa_Node/LoRa_Node.ino แล้ว Upload\n"
}

setup_mcp() {
  echo
  bold "AI chat client (Claude Code) -> client-mcp/.mcp.json"
  ask PI_HOST "Pi host/IP (ที่เครื่อง client ใช้ต่อ)" "$PI_HOST"
  ask HTTP_PORT "HTTP port ของ server บน Pi" "$HTTP_PORT"

  sed_file "$MCP_JSON" "s|\${PI_HOST:-[^}]*}|\${PI_HOST:-$PI_HOST}|;s|\${PI_PORT:-[^}]*}|\${PI_PORT:-$HTTP_PORT}|"
  info "client-mcp/.mcp.json"
  NEXT="$NEXT  MCP       : make client-install client-check && make claude\n"
}

setup_dashboard() {
  echo
  bold "Web dashboard -> dashboard/app.js"
  ask MQTT_WS_URL "MQTT WebSocket URL" "$MQTT_WS_URL"
  ask_topic
  ask_lora_ids

  sed_file "$APP_JS" "s|^  broker: \".*\",\$|  broker: \"$MQTT_WS_URL\",|;
s|^  prefix: \".*\",\$|  prefix: \"$TOPIC_PREFIX\",|;
s|^  appId: \".*\",\$|  appId: \"$LORA_APPLICATION_ID\",|;
s|^  devEui: \".*\",\$|  devEui: \"$DEV_EUI_LOWER\",|"
  info "dashboard/app.js (ถ้าเคยกด Save ใน browser ค่าเก่ายังถูกจำไว้ ให้แก้ในช่อง MQTT settings)"
  NEXT="$NEXT  Dashboard : make dashboard   (หรือเปิด http://<pi>:8000/)\n"
}

save_state() {
  cat >"$STATE" <<EOF
# Answers from 'make setup*' (git-ignored). Re-run to change.
TOPIC_PREFIX=$TOPIC_PREFIX
MQTT_HOST=$MQTT_HOST
MQTT_PORT=$MQTT_PORT
MQTT_WS_URL=$MQTT_WS_URL
LORA_APPLICATION_ID=$LORA_APPLICATION_ID
LORA_DEV_EUI=$LORA_DEV_EUI
LORA_APP_EUI=$LORA_APP_EUI
LORA_APP_KEY=$LORA_APP_KEY
PI_HOST=$PI_HOST
HTTP_PORT=$HTTP_PORT
SAMPLE_INTERVAL=$SAMPLE_INTERVAL
SIMULATE=$SIMULATE
EOF
  info ".env (เก็บคำตอบไว้เป็นค่า default ครั้งหน้า)"
}

# ---------------------------------------------------------------------------
[ $# -gt 0 ] || set -- pi arduino mcp dashboard
for part in "$@"; do
  case "$part" in
    pi | arduino | mcp | dashboard) ;;
    *) echo "ไม่รู้จัก '$part' (ใช้ได้: pi arduino mcp dashboard)" >&2; exit 1 ;;
  esac
done

echo
bold "IoT take-home setup: $*  (Enter = ใช้ค่าในวงเล็บ)"
NEXT=""
for part in "$@"; do
  "setup_$part"
done

echo
save_state

echo
bold "ขั้นต่อไป:"
printf '%b' "$NEXT"
echo
