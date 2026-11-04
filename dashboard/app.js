// Dashboard subscribes straight to the MQTT broker over WebSocket:
//   {prefix}/pi/...                                         <- Raspberry Pi
//   application/{appId}/device/{devEui}/event/up            <- ChirpStack (LoRa node)
const DEFAULTS = {
  broker: "wss://lora.kmitl.ac.th:8884/mqtt",
  prefix: "67070067",
  appId: "",
  devEui: "0a1930bd3503d95c",
};
const MAX_POINTS = 300;
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

const chart = new Chart($("chart"), {
  type: "line",
  data: {
    datasets: [
      { label: "Temperature (°C)", data: [], borderColor: "#e8693c", yAxisID: "y", tension: 0.3, pointRadius: 0 },
      { label: "Humidity (%)", data: [], borderColor: "#2f7de1", yAxisID: "y", tension: 0.3, pointRadius: 0 },
      { label: "Distance (cm)", data: [], borderColor: "#22a06b", yAxisID: "y1", tension: 0.3, pointRadius: 0 },
      { label: "Light raw (LoRa)", data: [], borderColor: "#b06ad9", yAxisID: "y1", tension: 0.3, pointRadius: 2 },
    ],
  },
  options: {
    animation: false,
    parsing: false,
    interaction: { mode: "nearest", intersect: false },
    scales: {
      x: {
        type: "linear",
        ticks: { callback: (v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
      },
      y: { position: "left", title: { display: true, text: "°C / %" } },
      y1: { position: "right", title: { display: true, text: "cm / light" }, grid: { drawOnChartArea: false } },
    },
  },
});

function addPoint(index, value) {
  const data = chart.data.datasets[index].data;
  data.push({ x: Date.now(), y: value });
  if (data.length > MAX_POINTS) data.shift();
  chart.update();
}

function setDot(id, ok) {
  $(id).classList.toggle("ok", !!ok);
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

// Same fallback as raspberry-pi/app/mqtt_bridge.py when ChirpStack has no codec
function decodeLora(dataB64) {
  const raw = Uint8Array.from(atob(dataB64 || ""), (c) => c.charCodeAt(0));
  if (raw.length < 3) return {};
  return { light_raw: (raw[0] << 8) | raw[1], light_digital: raw[2] };
}

function onUplink(text) {
  const msg = JSON.parse(text);
  const data = msg.object || decodeLora(msg.data);
  const rx = (msg.rxInfo || [{}])[0];
  $("light-raw").textContent = data.light_raw ?? "--";
  $("light-digital").textContent = data.light_digital ?? "--";
  $("rssi").textContent = rx.rssi ?? "--";
  $("snr").textContent = rx.snr ?? rx.loRaSNR ?? "--";
  $("fcnt").textContent = msg.fCnt ?? "--";
  $("lora-time").textContent = new Date().toLocaleTimeString();
  setDot("conn-lora", true);
  if (data.light_raw !== undefined) addPoint(3, data.light_raw);
}

function onMessage(topic, payload) {
  const t = topics();
  const text = payload.toString();
  const num = parseFloat(text);
  try {
    switch (topic) {
      case t.temperature:
        $("temperature").textContent = num.toFixed(1);
        addPoint(0, num);
        break;
      case t.humidity:
        $("humidity").textContent = num.toFixed(1);
        addPoint(1, num);
        break;
      case t.distance:
        $("distance").textContent = num.toFixed(1);
        addPoint(2, num);
        break;
      case t.led:
        $("led").checked = text === "on";
        $("led-text").textContent = text.toUpperCase();
        break;
      case t.status:
        setDot("conn-pi", text === "online");
        break;
      case t.uplink:
        onUplink(text);
        return;
      default:
        return;
    }
    $("pi-time").textContent = new Date().toLocaleTimeString();
  } catch (e) {
    console.error("bad message on", topic, e);
  }
}

function connect() {
  if (client) client.end(true);
  setDot("conn-mqtt", false);
  setDot("conn-pi", false);
  setDot("conn-lora", false);

  client = mqtt.connect(settings.broker, {
    clientId: "dashboard-" + Math.random().toString(16).slice(2, 10),
    reconnectPeriod: 3000,
  });

  client.on("connect", () => {
    setDot("conn-mqtt", true);
    const t = topics();
    const subs = [t.temperature, t.humidity, t.distance, t.led, t.status];
    if (t.uplink) subs.push(t.uplink);
    client.subscribe(subs, { qos: 1 });
  });
  client.on("close", () => setDot("conn-mqtt", false));
  client.on("error", (e) => console.error("mqtt error", e));
  client.on("message", onMessage);
}

$("led").addEventListener("change", (e) => {
  if (!client || !client.connected) {
    e.target.checked = !e.target.checked;
    alert("MQTT is not connected");
    return;
  }
  // The Pi switches the LED and publishes the new state on pi/device/led
  client.publish(topics().ledSet, e.target.checked ? "on" : "off", { qos: 1 });
});

const form = $("settings-form");
for (const [k, v] of Object.entries(settings)) form.elements[k].value = v;
if (!settings.appId) $("settings").open = true;

form.addEventListener("submit", (e) => {
  e.preventDefault();
  settings = Object.fromEntries(Object.keys(DEFAULTS).map((k) => [k, form.elements[k].value.trim()]));
  saveSettings(settings);
  connect();
});

connect();
