import struct
import threading
import time
from datetime import datetime, timezone, timedelta

from pymodbus.client import ModbusTcpClient

import db
import shared_state
from config import MachineConfig


def _parse_distance(raw: int) -> int:
    """Signed 16-bit big-endian, right-shifted 4 — matches Node-RED: buf.readInt16BE() >> 4"""
    signed = struct.unpack(">h", struct.pack(">H", raw))[0]
    return signed >> 4


def _run(machine: MachineConfig) -> None:
    state = "DISCONNECTED"
    last_product_time: datetime | None = None
    open_event_id: int | None = None
    prev_product: bool = False

    while True:
        if shared_state.get_demo_mode():
            time.sleep(1)
            continue

        client = ModbusTcpClient(machine.ip, port=502, timeout=3)
        try:
            if not client.connect():
                raise ConnectionError(f"TCP connect failed to {machine.ip}:502")

            result = client.read_holding_registers(address=machine.register_start, count=1)
            if result.isError():
                raise IOError(f"Modbus error on register {machine.register_start}: {result}")

            raw = result.registers[0]
            distance = _parse_distance(raw)
            product_present = distance >= machine.rest_distance
            now = datetime.now(timezone.utc)
            print(
                f"[{now.strftime('%H:%M:%S')}] {machine.machine_id} | "
                f"reg={machine.register_start} raw={raw} dist={distance} "
                f"threshold={machine.rest_distance} product={'YES' if product_present else 'NO'} "
                f"state={state}",
                flush=True,
            )

            # First successful read after startup or reconnect — leave DISCONNECTED immediately
            if state == "DISCONNECTED":
                state = "RUNNING"
                last_product_time = None  # reset timer so no false downtime on reconnect
                prev_product = False

            # Rising edge: new product breaking the beam
            if product_present and not prev_product:
                shared_state.increment_counter(machine.machine_id)
            prev_product = product_present

            if product_present:
                last_product_time = now
                if state == "DOWNTIME" and open_event_id is not None:
                    db.end_downtime_event(open_event_id, now)
                    open_event_id = None
                state = "RUNNING"
            else:
                if last_product_time is not None:
                    elapsed = (now - last_product_time).total_seconds()
                    if elapsed > machine.downtime_threshold and state == "RUNNING":
                        start_ts = last_product_time + timedelta(seconds=machine.downtime_threshold)
                        open_event_id = db.start_downtime_event(machine.machine_id, start_ts)
                        state = "DOWNTIME"

            shared_state.update_machine(machine.machine_id, state, distance)

        except Exception as exc:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] {machine.machine_id} | "
                f"ERROR ({type(exc).__name__}): {exc} — retrying in 5s",
                flush=True,
            )
            if state != "DISCONNECTED":
                if state == "DOWNTIME" and open_event_id is not None:
                    db.end_downtime_event(open_event_id, datetime.now(timezone.utc))
                    open_event_id = None
                state = "DISCONNECTED"
            prev_product = False
            shared_state.update_machine(machine.machine_id, "DISCONNECTED")
            time.sleep(5)
            continue

        finally:
            try:
                client.close()
            except Exception:
                pass

        time.sleep(1)


def start_poller_thread(machine: MachineConfig) -> threading.Thread:
    t = threading.Thread(
        target=_run, args=(machine,), daemon=True, name=f"poller-{machine.machine_id}"
    )
    t.start()
    return t
