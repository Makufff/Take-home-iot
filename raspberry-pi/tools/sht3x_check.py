"""SHT3x (I2C 0x44) check. Stop main.py first, then on the Pi:

    cd raspberry-pi && source python3.11/bin/activate
    python -m tools.sht3x_check
"""
import time

from app.hardware import SHT3x


def main():
    sensor = SHT3x()
    try:
        for i in range(5):
            try:
                t, h = sensor.read()
                print(f"{i + 1}: OK  temperature={t} °C humidity={h} %")
            except IOError as e:
                print(f"{i + 1}: FAIL {e}")
            time.sleep(1)
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
