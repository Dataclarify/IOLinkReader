import threading
import time

_lock = threading.Lock()
_demo_mode: bool = False
_machines: dict = {}   # machine_id -> {status, distance, updated_at}
_counters: dict = {}   # machine_id -> int  (product count, rising-edge)


def set_demo_mode(value: bool) -> None:
    global _demo_mode
    with _lock:
        _demo_mode = value


def get_demo_mode() -> bool:
    with _lock:
        return _demo_mode


def update_machine(machine_id: str, status: str, distance: int | None = None) -> None:
    with _lock:
        _machines[machine_id] = {
            "status": status,
            "distance": distance,
            "updated_at": time.time(),
        }


def get_machine(machine_id: str) -> dict:
    with _lock:
        return dict(_machines.get(machine_id, {"status": "DISCONNECTED", "distance": None, "updated_at": None}))


def get_all() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _machines.items()}


def increment_counter(machine_id: str) -> None:
    with _lock:
        _counters[machine_id] = _counters.get(machine_id, 0) + 1


def reset_counter(machine_id: str) -> None:
    with _lock:
        _counters[machine_id] = 0


def get_counter(machine_id: str) -> int:
    with _lock:
        return _counters.get(machine_id, 0)
