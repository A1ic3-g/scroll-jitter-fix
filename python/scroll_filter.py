#!/usr/bin/env python3
import time
import uinput
from evdev import InputDevice, list_devices, ecodes

TARGET_NAME = "Newmen"

# Search for the real mouse
def find_mouse_device():
    for path in list_devices():
        dev = InputDevice(path)
        caps = dev.capabilities()
        if TARGET_NAME in dev.name and ecodes.EV_REL in caps:
            rels = caps[ecodes.EV_REL]
            if ecodes.REL_WHEEL in rels:
                return dev
    raise RuntimeError("No suitable mouse device found.")

mouse = find_mouse_device()
print(f"Using device: {mouse.name} ({mouse.path})")
mouse.grab()  # Block original device input

# Define buttons and motion
KEYS = [
    uinput.BTN_LEFT,
    uinput.BTN_RIGHT,
    uinput.BTN_MIDDLE,
    uinput.BTN_SIDE,
    uinput.BTN_EXTRA
]
REL = [
    uinput.REL_X,
    uinput.REL_Y,
    uinput.REL_WHEEL
]
uinput_dev = uinput.Device(REL + KEYS)

# Logging to avoid stdout latency
log_file = open("/tmp/scroll_filter.log", "a", buffering=1)

# Scroll filtering class
class ScrollFilter:
    def __init__(self):
        self.second_last = None
        self.last = None
        self.passed = 0
        self.suppressed = 0
        self.last_print = time.time()

    def filter(self, direction):
        if self.second_last is not None:
            if self.second_last == self.last and self.last != direction:
                self.suppressed += 1
                self.second_last = self.last
                self.last = direction
                self._maybe_log()
                return None
        self.passed += 1
        self.second_last = self.last
        self.last = direction
        self._maybe_log()
        return direction

    def _maybe_log(self):
        now = time.time()
        if now - self.last_print >= 5.0:
            log_file.write(f"[filter] passed: {self.passed}, suppressed: {self.suppressed}\n")
            self.last_print = now

# Two-pass filter
filter1 = ScrollFilter()
filter2 = ScrollFilter()

for event in mouse.read_loop():
    emitted = False

    if event.type == ecodes.EV_REL:
        if event.code == ecodes.REL_WHEEL:
            direction = event.value

            # Run through both filters
            filtered = filter1.filter(direction)
            if filtered is not None:
                filtered = filter2.filter(filtered)
                if filtered is not None:
                    uinput_dev.emit((ecodes.EV_REL, ecodes.REL_WHEEL), filtered, syn=False)
                    emitted = True

        elif event.code in (ecodes.REL_X, ecodes.REL_Y):
            uinput_dev.emit((event.type, event.code), event.value, syn=False)
            emitted = True

    elif event.type == ecodes.EV_KEY and event.code in (
        ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE,
        ecodes.BTN_SIDE, ecodes.BTN_EXTRA
    ):
        uinput_dev.emit((event.type, event.code), event.value, syn=False)
        emitted = True

    # Only send SYN_REPORT once per event loop iteration
    if emitted:
        uinput_dev.syn()
