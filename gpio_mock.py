# gpio_mock.py
import time
import random

class GPIO:
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    HIGH = True
    LOW = False

    _states = {}

    @staticmethod
    def setmode(mode):
        print(f"[MOCK] GPIO.setmode({mode})")

    @staticmethod
    def setup(pin, mode):
        print(f"[MOCK] GPIO.setup({pin}, {mode})")
        if mode == GPIO.IN:
            GPIO._states[pin] = False

    @staticmethod
    def output(pin, state):
        GPIO._states[pin] = state
        print(f"[MOCK] GPIO {pin} → {'ON' if state else 'OFF'}")

    @staticmethod
    def input(pin):
        # Simula PIR
        if pin == 17:
            return random.choice([0, 0, 0, 1])  # 25% chance de movimento
        return GPIO._states.get(pin, False)

    @staticmethod
    def cleanup():
        print("[MOCK] GPIO.cleanup()")

# Mock DHT22
class DHT22:
    def __init__(self, pin):
        self.pin = pin
        print(f"[MOCK] DHT22 no pino {pin}")

    def read(self):
        temp = round(20 + random.uniform(-2, 5), 1)
        humidity = round(40 + random.uniform(-10, 20), 1)
        return temp, humidity