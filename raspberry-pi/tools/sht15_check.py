"""SHT15 wiring check. Stop main.py first, then on the Pi:

    cd raspberry-pi && source .venv/bin/activate
    python -m tools.sht15_check
"""
import subprocess

import RPi.GPIO as GPIO

from app import config
from app.hardware import SHT15


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "(not available)"


def idle_level(pin):
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    return GPIO.input(pin)


def try_read(data_pin, sck_pin):
    try:
        sensor = SHT15(GPIO, data_pin, sck_pin)
        t, h = sensor.read()
        return f"OK  temperature={t} °C humidity={h} %"
    except (IOError, TimeoutError) as e:
        return f"FAIL {e}"


def main():
    print("1) I2C enabled? (raspi-config: 0 = enabled, 1 = disabled):", run(["raspi-config", "nonint", "get_i2c"]))
    print("   pin functions:", run(["pinctrl", "get", "2,3"]) or run(["raspi-gpio", "get", "2,3"]))

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    d, s = config.PIN_SHT15_DATA, config.PIN_SHT15_SCK
    print(f"2) idle level with pull-up (should be 1): GPIO{d}={idle_level(d)} GPIO{s}={idle_level(s)}")
    print("   0 on DATA = wire shorted to GND, sensor not powered, or wrong pin")

    print(f"3) read with DATA=GPIO{d}, SCK=GPIO{s}:", try_read(d, s))
    print(f"4) read with pins swapped DATA=GPIO{s}, SCK=GPIO{d}:", try_read(s, d))
    print("   if only (4) is OK: DATA and SCK are swapped in the wiring")
    GPIO.cleanup()


if __name__ == "__main__":
    main()
