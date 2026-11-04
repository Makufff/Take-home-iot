"""Local devices on the Raspberry Pi: SHT3x, HC-SR04 and LED."""
import random
import threading
import time

from . import config


class SHT3x:
    """Sensirion SHT3x over I2C (/dev/i2c-1: GPIO2 = SDA, GPIO3 = SCL).

    Uses the kernel i2c-dev interface directly, so no extra package is needed.
    Requires I2C enabled (raspi-config nonint do_i2c 0).
    """

    I2C_SLAVE = 0x0703
    CMD_MEASURE = b"\x24\x00"  # single shot, high repeatability, no clock stretching

    def __init__(self, bus=1, address=0x44):
        import fcntl
        import os

        self._os = os
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        fcntl.ioctl(self.fd, self.I2C_SLAVE, address)

    @staticmethod
    def _crc(data):
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        return crc

    def read(self):
        try:
            self._os.write(self.fd, self.CMD_MEASURE)
            time.sleep(0.02)  # max 15.5 ms for high repeatability
            raw = self._os.read(self.fd, 6)
        except OSError as e:
            raise IOError(f"SHT3x I2C error: {e}") from e
        if len(raw) != 6 or self._crc(raw[0:2]) != raw[2] or self._crc(raw[3:5]) != raw[5]:
            raise IOError("SHT3x CRC mismatch")
        temperature = -45 + 175 * ((raw[0] << 8) | raw[1]) / 65535
        humidity = 100 * ((raw[3] << 8) | raw[4]) / 65535
        return round(temperature, 2), round(max(0.0, min(100.0, humidity)), 2)

    def close(self):
        self._os.close(self.fd)


class HCSR04:
    TIMEOUT = 0.04  # ~6.8 m round trip

    def __init__(self, gpio, trigger_pin, echo_pin):
        self.gpio = gpio
        self.trigger = trigger_pin
        self.echo = echo_pin
        gpio.setup(trigger_pin, gpio.OUT, initial=gpio.LOW)
        gpio.setup(echo_pin, gpio.IN)

    def _single(self):
        gpio = self.gpio
        gpio.output(self.trigger, 1)
        time.sleep(0.00001)
        gpio.output(self.trigger, 0)

        deadline = time.monotonic() + self.TIMEOUT
        while gpio.input(self.echo) == 0:
            if time.monotonic() > deadline:
                return None
        start = time.monotonic()
        while gpio.input(self.echo) == 1:
            if time.monotonic() - start > self.TIMEOUT:
                return None
        return (time.monotonic() - start) * 34300 / 2

    def read(self, samples=3):
        values = []
        for _ in range(samples):
            d = self._single()
            if d is not None:
                values.append(d)
            time.sleep(0.06)
        if not values:
            return None
        values.sort()
        return round(values[len(values) // 2], 1)


class PiDevices:
    """Thread-safe access to all local devices."""

    def __init__(self):
        self._lock = threading.Lock()
        self._led = False
        if config.SIMULATE:
            self.gpio = None
            return

        import RPi.GPIO as GPIO

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.gpio = GPIO
        GPIO.setup(config.PIN_LED, GPIO.OUT, initial=GPIO.LOW)
        self.sht3x = SHT3x()
        self.ultrasonic = HCSR04(GPIO, config.PIN_TRIGGER, config.PIN_ECHO)

    def read_sensors(self):
        with self._lock:
            if self.gpio is None:
                return {
                    "temperature": round(random.uniform(25, 31), 2),
                    "humidity": round(random.uniform(50, 70), 2),
                    "distance": round(random.uniform(20, 150), 1),
                }
            result = {"temperature": None, "humidity": None, "distance": None}
            try:
                result["temperature"], result["humidity"] = self.sht3x.read()
            except (IOError, TimeoutError) as e:
                print(f"[hardware] SHT3x error: {e}")
            result["distance"] = self.ultrasonic.read()
            return result

    @property
    def led(self):
        return self._led

    def set_led(self, on):
        with self._lock:
            self._led = bool(on)
            if self.gpio is not None:
                self.gpio.output(config.PIN_LED, 1 if self._led else 0)
            return self._led

    def close(self):
        if self.gpio is not None:
            self.sht3x.close()
            self.gpio.cleanup()
