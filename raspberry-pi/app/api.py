"""REST API used by the web dashboard."""
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .service import IoTService


class LedRequest(BaseModel):
    on: bool


def create_api(service: IoTService) -> FastAPI:
    api = FastAPI(title="Raspberry Pi IoT API")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @api.get("/api/status")
    def status():
        return service.status()

    @api.get("/api/history")
    def history(minutes: float = 15):
        since = time.time() - minutes * 60
        return [h for h in service.history if h["updated_at"] >= since]

    @api.post("/api/pi/sensors/read")
    def read_now():
        return service.read_pi_sensors()

    @api.post("/api/pi/led")
    def pi_led(req: LedRequest):
        return {"led": service.set_pi_led(req.on)}

    if config.DASHBOARD_DIR.is_dir():
        api.mount("/", StaticFiles(directory=config.DASHBOARD_DIR, html=True), name="dashboard")

    return api
