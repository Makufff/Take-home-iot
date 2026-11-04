// API base: same origin when served by the Pi, or ?api=http://<pi-ip>:8000
const params = new URLSearchParams(location.search);
const API = (params.get("api") || "").replace(/\/$/, "");
const POLL_MS = 3000;

const $ = (id) => document.getElementById(id);

const chart = new Chart($("chart"), {
  type: "line",
  data: {
    datasets: [
      { label: "Temperature (°C)", data: [], borderColor: "#e8693c", yAxisID: "y", tension: 0.3, pointRadius: 0 },
      { label: "Humidity (%)", data: [], borderColor: "#2f7de1", yAxisID: "y", tension: 0.3, pointRadius: 0 },
      { label: "Distance (cm)", data: [], borderColor: "#22a06b", yAxisID: "y1", tension: 0.3, pointRadius: 0 },
    ],
  },
  options: {
    animation: false,
    parsing: false,
    interaction: { mode: "index", intersect: false },
    scales: {
      x: {
        type: "linear",
        ticks: { callback: (v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
      },
      y: { position: "left", title: { display: true, text: "°C / %" } },
      y1: { position: "right", title: { display: true, text: "cm" }, grid: { drawOnChartArea: false } },
    },
  },
});

function fmt(v, digits = 1) {
  return v === null || v === undefined ? "--" : Number(v).toFixed(digits);
}

function fmtTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleTimeString() : "--";
}

async function api(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

function setDot(id, ok) {
  $(id).classList.toggle("ok", !!ok);
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    setDot("conn-api", true);
    setDot("conn-mqtt", s.mqtt.connected);
    setDot("conn-lora", s.lora.connected);

    $("temperature").textContent = fmt(s.pi.temperature);
    $("humidity").textContent = fmt(s.pi.humidity);
    $("distance").textContent = fmt(s.pi.distance);
    $("led").checked = s.pi.led;
    $("led-text").textContent = s.pi.led ? "ON" : "OFF";
    $("pi-time").textContent = fmtTime(s.pi.updated_at);
    $("simulate").textContent = s.simulate ? "(simulate mode)" : "";

    const n = s.lora.node || {};
    $("light-raw").textContent = n.light_raw ?? "--";
    $("light-digital").textContent = n.light_digital ?? "--";
    $("rssi").textContent = n.rssi ?? "--";
    $("snr").textContent = n.snr ?? "--";
    $("lora-time").textContent = fmtTime(n.received_at);
  } catch (e) {
    setDot("conn-api", false);
    console.error(e);
  }
}

async function refreshHistory() {
  try {
    const rows = await api("/api/history?minutes=15");
    const keys = ["temperature", "humidity", "distance"];
    keys.forEach((k, i) => {
      chart.data.datasets[i].data = rows
        .filter((r) => r[k] !== null)
        .map((r) => ({ x: r.updated_at * 1000, y: r[k] }));
    });
    chart.update();
  } catch (e) {
    console.error(e);
  }
}

$("led").addEventListener("change", async (e) => {
  const on = e.target.checked;
  try {
    const r = await api("/api/pi/led", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on }),
    });
    $("led-text").textContent = r.led ? "ON" : "OFF";
  } catch (err) {
    e.target.checked = !on;
    alert("LED control failed: " + err.message);
  }
});

function tick() {
  refreshStatus();
  refreshHistory();
}

tick();
setInterval(tick, POLL_MS);
