"""Local devices on the Raspberry Pi: SHT15, HC-SR04 and LED."""
import random
import threading
import time

from . import config


class SHT15:
    """Sensirion SHT1x bit-banged 2-wire protocol (not I2C).

    DATA is driven low as an output and released (input + pull-up) for high,
    so the sensor can pull it low for ACK and data-ready.
    """

    CMD_TEMPERATURE = 0x03
    CMD_HUMIDITY = 0x05
    CMD_SOFT_RESET = 0x1E

    # Datasheet coefficients: VDD 3.3V (d1 interpolated), 14-bit T, 12-bit RH
    D1 = -39.66
    D2 = 0.01
    C1, C2, C3 = -2.0468, 0.0367, -1.5955e-6
    T1, T2 = 0.01, 0.00008

    def __init__(self, gpio, data_pin, sck_pin):
        self.gpio = gpio
        self.data = data_pin
        self.sck = sck_pin
        gpio.setup(sck_pin, gpio.OUT, initial=gpio.LOW)
        self._release()
        self._reset_connection()

    def _release(self):
        self.gpio.setup(self.data, self.gpio.IN, pull_up_down=self.gpio.PUD_UP)

    def _low(self):
        self.gpio.setup(self.data, self.gpio.OUT, initial=self.gpio.LOW)

    def _clock(self, level):
        self.gpio.output(self.sck, level)
        time.sleep(0.000002)

    def _reset_connection(self):
        self._release()
        for _ in range(9):
            self._clock(1)
            self._clock(0)

    def _start(self):
        # DATA falls while SCK high, SCK pulses, DATA rises while SCK high
        self._release()
        self._clock(1)
        self._low()
        self._clock(0)
        self._clock(1)
        self._release()
        self._clock(0)

    def _send_byte(self, value):
        for i in range(7, -1, -1):
            if value & (1 << i):
                self._release()
            else:
                self._low()
            self._clock(1)
            self._clock(0)
        self._release()
        self._clock(1)
        ack = self.gpio.input(self.data) == 0
        self._clock(0)
        if not ack:
            raise IOError("SHT15 did not ACK command")

    def _read_byte(self, ack):
        value = 0
        self._release()
        for _ in range(8):
            self._clock(1)
            value = (value << 1) | self.gpio.input(self.data)
            self._clock(0)
        if ack:
            self._low()
        self._clock(1)
        self._clock(0)
        self._release()
        return value

    def _measure(self, command):
        self._start()
        self._send_byte(command)
        deadline = time.monotonic() + 0.5
        while self.gpio.input(self.data):
            if time.monotonic() > deadline:
                self._reset_connection()
                raise TimeoutError("SHT15 measurement timeout")
            time.sleep(0.005)
        msb = self._read_byte(ack=True)
        lsb = self._read_byte(ack=False)  # skip CRC
        return (msb << 8) | lsb

    def read(self):
        so_t = self._measure(self.CMD_TEMPERATURE)
        temperature = self.D1 + self.D2 * so_t
        so_rh = self._measure(self.CMD_HUMIDITY)
        rh_linear = self.C1 + self.C2 * so_rh + self.C3 * so_rh * so_rh
        humidity = (temperature - 25) * (self.T1 + self.T2 * so_rh) + rh_linear
        return round(temperature, 2), round(max(0.0, min(100.0, humidity)), 2)


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
        self.sht15 = SHT15(GPIO, config.PIN_SHT15_DATA, config.PIN_SHT15_SCK)
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
                result["temperature"], result["humidity"] = self.sht15.read()
            except (IOError, TimeoutError) as e:
                print(f"[hardware] SHT15 error: {e}")
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
            self.gpio.cleanup()
