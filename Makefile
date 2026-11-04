# IoT take-home: run 'make setup' first, then the targets for the machine you are on.
#   make help

-include .env

TOPIC_PREFIX        ?= 67070067
MQTT_HOST           ?= lora.kmitl.ac.th
MQTT_PORT           ?= 1883
LORA_APPLICATION_ID ?=
LORA_DEV_EUI        ?= 0a1930bd3503d95c
PI_HOST             ?= raspberrypi.local
HTTP_PORT           ?= 8000
DASHBOARD_PORT      ?= 8080

PI_DIR     := raspberry-pi
CLIENT_DIR := client-mcp
PI_PY      := $(PI_DIR)/.venv/bin/python
CLIENT_PY  := $(CLIENT_DIR)/.venv/bin/python
SERVICE    := pi-iot
DEV_EUI    := $(shell printf '%s' '$(LORA_DEV_EUI)' | tr '[:upper:]' '[:lower:]')

.DEFAULT_GOAL := help
.PHONY: help setup setup-pi setup-arduino setup-mcp setup-dashboard pi-apt pi-install pi-run pi-sim pi-service pi-service-remove pi-logs \
        pi-i2c sht3x-check status client-install client-check claude claude-add \
        dashboard mqtt-sub lora-sub led-on led-off clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Ask for all settings and write every config file
	@bash scripts/setup.sh

setup-pi: ## Ask for Pi settings -> raspberry-pi/.env
	@bash scripts/setup.sh pi

setup-arduino: ## Ask for LoRa keys -> arduino-lora/LoRa_Node/secrets.h
	@bash scripts/setup.sh arduino

setup-mcp: ## Ask for Pi address -> client-mcp/.mcp.json
	@bash scripts/setup.sh mcp

setup-dashboard: ## Ask for MQTT/LoRa ids -> dashboard/app.js defaults
	@bash scripts/setup.sh dashboard

# --- Raspberry Pi ------------------------------------------------------------

pi-apt: ## [Pi] Install system packages (sudo)
	sudo apt update
	sudo apt install -y git python3-venv python3-rpi-lgpio mosquitto-clients i2c-tools

pi-install: ## [Pi] Create venv and install Python packages
	@test -f $(PI_DIR)/.env || { echo "ไม่มี $(PI_DIR)/.env: รัน 'make setup' ก่อน"; exit 1; }
	test -d $(PI_DIR)/.venv || python3 -m venv --system-site-packages $(PI_DIR)/.venv
	$(PI_PY) -m pip install -r $(PI_DIR)/requirements.txt

pi-run: ## [Pi] Run MCP + REST + dashboard server
	cd $(PI_DIR) && .venv/bin/python main.py

pi-sim: ## Run the server with fake sensors (no GPIO, e.g. on a laptop)
	cd $(PI_DIR) && SIMULATE=1 .venv/bin/python main.py

pi-service: ## [Pi] Install and start systemd service (start on boot)
	@printf '%s\n' \
	  '[Unit]' \
	  'Description=Pi IoT MCP server' \
	  'After=network-online.target' \
	  'Wants=network-online.target' \
	  '' \
	  '[Service]' \
	  'User=$(shell id -un)' \
	  'WorkingDirectory=$(CURDIR)/$(PI_DIR)' \
	  'ExecStart=$(CURDIR)/$(PI_PY) main.py' \
	  'Restart=on-failure' \
	  '' \
	  '[Install]' \
	  'WantedBy=multi-user.target' \
	  | sudo tee /etc/systemd/system/$(SERVICE).service >/dev/null
	sudo systemctl daemon-reload
	sudo systemctl enable --now $(SERVICE)
	sudo systemctl restart $(SERVICE)
	@echo "ดู log: make pi-logs"

pi-service-remove: ## [Pi] Stop and remove systemd service
	-sudo systemctl disable --now $(SERVICE)
	sudo rm -f /etc/systemd/system/$(SERVICE).service
	sudo systemctl daemon-reload

pi-logs: ## [Pi] Follow service logs
	journalctl -u $(SERVICE) -f

pi-i2c: ## [Pi] Enable I2C for the SHT3x (reboot afterwards)
	sudo raspi-config nonint do_i2c 0
	@echo "เปิด I2C แล้ว: sudo reboot แล้วเช็กด้วย i2cdetect -y 1 (ต้องเจอ 0x44)"

sht3x-check: ## [Pi] SHT3x (I2C 0x44) check (stop the server first)
	cd $(PI_DIR) && .venv/bin/python -m tools.sht3x_check

status: ## GET /api/status from the Pi
	curl -s http://$(PI_HOST):$(HTTP_PORT)/api/status; echo

# --- AI chat client (Claude Code) --------------------------------------------

client-install: ## Create venv for client-mcp/check_connection.py
	test -d $(CLIENT_DIR)/.venv || python3 -m venv $(CLIENT_DIR)/.venv
	$(CLIENT_PY) -m pip install -r $(CLIENT_DIR)/requirements.txt

client-check: ## Test MCP connection to the Pi
	cd $(CLIENT_DIR) && PI_HOST=$(PI_HOST) PI_PORT=$(HTTP_PORT) .venv/bin/python check_connection.py

claude: ## Open Claude Code in client-mcp (uses pi-iot MCP server)
	cd $(CLIENT_DIR) && PI_HOST=$(PI_HOST) PI_PORT=$(HTTP_PORT) claude

claude-add: ## Add pi-iot MCP server to Claude Code for all projects
	claude mcp add --transport http --scope user pi-iot http://$(PI_HOST):$(HTTP_PORT)/mcp

# --- Dashboard / MQTT --------------------------------------------------------

dashboard: ## Serve dashboard locally on DASHBOARD_PORT (default 8080)
	@echo "เปิด http://localhost:$(DASHBOARD_PORT)"
	cd dashboard && python3 -m http.server $(DASHBOARD_PORT)

mqtt-sub: ## Subscribe to all Pi topics
	mosquitto_sub -h $(MQTT_HOST) -p $(MQTT_PORT) -v -t "$(TOPIC_PREFIX)/#"

lora-sub: ## Subscribe to LoRa uplinks from ChirpStack
	@test -n "$(LORA_APPLICATION_ID)" || { echo "ยังไม่ได้ตั้ง LORA_APPLICATION_ID: รัน 'make setup'"; exit 1; }
	mosquitto_sub -h $(MQTT_HOST) -p $(MQTT_PORT) -v \
	  -t "application/$(LORA_APPLICATION_ID)/device/$(DEV_EUI)/event/up"

led-on: ## Turn the Pi LED on via MQTT
	mosquitto_pub -h $(MQTT_HOST) -p $(MQTT_PORT) -t "$(TOPIC_PREFIX)/pi/device/led/set" -m on

led-off: ## Turn the Pi LED off via MQTT
	mosquitto_pub -h $(MQTT_HOST) -p $(MQTT_PORT) -t "$(TOPIC_PREFIX)/pi/device/led/set" -m off

clean: ## Remove venvs and Python caches
	rm -rf $(PI_DIR)/.venv $(CLIENT_DIR)/.venv
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
