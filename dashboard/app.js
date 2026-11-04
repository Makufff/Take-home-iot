// Dashboard subscribes straight to the MQTT broker over WebSocket:
//   {prefix}/pi/...                                         <- Raspberry Pi
//   application/{appId}/device/{devEui}/event/up            <- ChirpStack (LoRa node)
const DEFAULTS = {
  broker: "wss://lora.kmitl.ac.th:8884/mqtt",
  prefix: "67070067",
  appId: "ec9359bc-fc1f-4f01-a3f0-9ceda917d84d",
  devEui: "0a1930bd3503d95c",
};
const MAX_POINTS = 120;
const LORA_STALE_MS = 3 * 60 * 1000; // node sends every ~60 s
const STORAGE_KEY = "iot-dashboard-settings";

const $ = (id) => document.getElementById(id);

function loadSettings() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

function saveSettings(s) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // private mode etc: settings only last for this page load
  }
}

let settings = loadSettings();
let client = null;
let lastUplinkAt = null;

// ---------- sparklines ----------
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function sparkline(canvasId, colorVar, unit) {
  const color = cssVar(colorVar);
  const ctx = $(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [{
        data: [],
        borderColor: color,
        borderWidth: 2,
        tension: 0.35,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: true,
        backgroundColor: (c) => {
          const { chartArea } = c.chart;
          if (!chartArea) return "transparent";
          const g = c.chart.ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          g.addColorStop(0, color + "55");
          g.addColorStop(1, color + "00");
          return g;
        },
      }],
    },
    options: {
      animation: false,
      parsing: false,
      maintainAspectRatio: false,
      layout: { padding: { top: 6 } },
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (items) => new Date(items[0].parsed.x).toLocaleTimeString(),
            label: (item) => `${item.parsed.y} ${unit}`,
          },
        },
      },
      scales: { x: { type: "linear", display: false }, y: { display: false, grace: "10%" } },
    },
  });
}

const sparks = {
  temperature: sparkline("spark-temperature", "--temp", "°C"),
  humidity: sparkline("spark-humidity", "--hum", "%RH"),
  distance: sparkline("spark-distance", "--dist", "cm"),
  light: sparkline("spark-light", "--light", "raw"),
};

function addPoint(name, value) {
  const data = sparks[name].data.datasets[0].data;
  data.push({ x: Date.now(), y: value });
  if (data.length > MAX_POINTS) data.shift();
  sparks[name].update();
}

// ---------- helpers ----------
function setText(id, text) {
  const el = $(id);
  if (el.textContent === String(text)) return;
  el.textContent = text;
  el.classList.remove("flash");
  void el.offsetWidth; // restart the animation
  el.classList.add("flash");
}

function setPill(id, state) {
  $(id).classList.toggle("ok", state === "ok");
  $(id).classList.toggle("stale", state === "stale");
}

function now() {
  return new Date().toLocaleTimeString();
}

function signalLevel(rssi) {
  if (rssi == null) return 0;
  if (rssi > -90) return 4;
  if (rssi > -100) return 3;
  if (rssi > -110) return 2;
  return 1;
}

function topics() {
  const p = settings.prefix ? settings.prefix.replace(/\/$/, "") + "/" : "";
  return {
    temperature: p + "pi/sensor/temperature",
    humidity: p + "pi/sensor/humidity",
    distance: p + "pi/sensor/distance",
    led: p + "pi/device/led",
    ledSet: p + "pi/device/led/set",
    status: p + "pi/status",
    uplink: settings.appId
      ? `application/${settings.appId}/device/${settings.devEui.toLowerCase()}/event/up`
      : null,
  };
}

// ---------- LoRa ----------
// Same decoder as raspberry-pi/app/mqtt_bridge.py: [light_raw_hi, light_raw_lo, light_digital]
function decodeLora(dataB64) {
  const raw = Uint8Array.from(atob(dataB64 || ""), (c) => c.charCodeAt(0));
  if (raw.length < 3) return {};
  return { light_raw: (raw[0] << 8) | raw[1], light_digital: raw[2] };
}

function onUplink(text) {
  const msg = JSON.parse(text);
  // Decode the raw bytes ourselves so a mismatched ChirpStack codec can't hide light_raw.
  let data = decodeLora(msg.data);
  if (data.light_raw === undefined && msg.object) data = msg.object;
  const rx = (msg.rxInfo || [{}])[0];
  const rssi = rx.rssi ?? null;

  setText("rssi", rssi ?? "--");
  setText("snr", rx.snr ?? rx.loRaSNR ?? "--");
  setText("fcnt", msg.fCnt ?? "--");
  $("signal-bars").dataset.level = signalLevel(rssi);
  $("lora-time").textContent = now();
  lastUplinkAt = Date.now();
  setPill("conn-lora", "ok");

  // MAC-only uplinks carry no sensor data: keep showing the last light reading
  if (data.light_raw === undefined) return;
  setText("light-raw", data.light_raw);
  setText("light-digital", data.light_digital ?? "--");
  $("light-bar").style.width = `${Math.min(100, (data.light_raw / 1023) * 100)}%`;
  addPoint("light", data.light_raw);
}

// ---------- MQTT ----------
function onMessage(topic, payload) {
  const t = topics();
  const text = payload.toString();
  const num = parseFloat(text);
  try {
    switch (topic) {
      case t.temperature:
      case t.humidity:
      case t.distance: {
        const name = Object.keys(t).find((k) => t[k] === topic);
        if (Number.isNaN(num)) return;
        setText(name, num.toFixed(1));
        addPoint(name, num);
        break;
      }
      case t.led: {
        const on = text === "on";
        $("led").checked = on;
        $("led-tile").classList.toggle("on", on);
        setText("led-text", on ? "เปิด" : "ปิด");
        break;
      }
      case t.status:
        setPill("conn-pi", text === "online" ? "ok" : "");
        return;
      case t.uplink:
        onUplink(text);
        return;
      default:
        return;
    }
    $("pi-time").textContent = now();
  } catch (e) {
    console.error("bad message on", topic, e);
  }
}

function connect() {
  if (client) client.end(true);
  setPill("conn-mqtt", "");
  setPill("conn-pi", "");
  setPill("conn-lora", "");

  client = mqtt.connect(settings.broker, {
    clientId: "dashboard-" + Math.random().toString(16).slice(2, 10),
    reconnectPeriod: 3000,
  });

  client.on("connect", () => {
    setPill("conn-mqtt", "ok");
    const t = topics();
    const subs = [t.temperature, t.humidity, t.distance, t.led, t.status];
    if (t.uplink) subs.push(t.uplink);
    client.subscribe(subs, { qos: 1 });
  });
  client.on("close", () => setPill("conn-mqtt", ""));
  client.on("error", (e) => console.error("mqtt error", e));
  client.on("message", onMessage);
}

// ---------- clock + LoRa freshness ----------
function tick() {
  $("clock").textContent = now();
  if (lastUplinkAt) {
    const s = Math.round((Date.now() - lastUplinkAt) / 1000);
    $("lora-ago").textContent = s < 60 ? `(${s} วินาทีที่แล้ว)` : `(${Math.floor(s / 60)} นาที ${s % 60} วินาทีที่แล้ว)`;
    if (Date.now() - lastUplinkAt > LORA_STALE_MS) setPill("conn-lora", "stale");
  }
}
setInterval(tick, 1000);
tick();

// ---------- controls ----------
$("led").addEventListener("change", (e) => {
  if (!client || !client.connected) {
    e.target.checked = !e.target.checked;
    alert("ยังไม่ได้เชื่อมต่อ MQTT");
    return;
  }
  // The Pi switches the LED and publishes the new state on pi/device/led
  client.publish(topics().ledSet, e.target.checked ? "on" : "off", { qos: 1 });
});

$("settings-btn").addEventListener("click", () => {
  $("settings").hidden = !$("settings").hidden;
});

const form = $("settings-form");
for (const [k, v] of Object.entries(settings)) form.elements[k].value = v;
if (!settings.appId) $("settings").hidden = false;

form.addEventListener("submit", (e) => {
  e.preventDefault();
  settings = Object.fromEntries(Object.keys(DEFAULTS).map((k) => [k, form.elements[k].value.trim()]));
  saveSettings(settings);
  $("settings").hidden = true;
  connect();
});

connect();
