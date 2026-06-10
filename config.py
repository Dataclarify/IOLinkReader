import configparser
import os
import sys
from dataclasses import dataclass


@dataclass
class MachineConfig:
    section: str
    ip: str
    machine_id: str
    machine_name: str
    port: int
    register_start: int
    rest_distance: int
    downtime_threshold: int
    live: bool


@dataclass
class AppConfig:
    machines: list[MachineConfig]
    refresh_interval: int


def _app_data_dir() -> str:
    data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DataClarify")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _config_path() -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(_app_data_dir(), "config.txt")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt")


def load_config(path: str | None = None) -> AppConfig:
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    target = path or _config_path()
    if not cfg.read(target):
        raise FileNotFoundError(f"config.txt not found at {target}")

    machines: list[MachineConfig] = []
    for section in cfg.sections():
        if section.lower() == "global":
            continue
        port = int(cfg[section]["Port"])
        # Register_Start is optional — derived from Port if omitted.
        # Keyence NQ-MP8L/EP4L register map: Port N starts at register 2 + (N-1)*16
        # Port 1→2, Port 2→18, Port 3→34, Port 4→50
        register_start = int(cfg[section]["Register_Start"]) if "Register_Start" in cfg[section] else 2 + (port - 1) * 16
        machines.append(MachineConfig(
            section=section,
            ip=cfg[section]["IP"].strip(),
            machine_id=cfg[section]["Machine_ID"].strip(),
            machine_name=cfg[section]["Machine_Name"].strip(),
            port=port,
            register_start=register_start,
            rest_distance=int(cfg[section]["Rest_Distance"]),
            downtime_threshold=int(cfg[section]["Downtime_Threshold"]),
            live=cfg[section].get("Live", "true").strip().lower() == "true",
        ))

    if not machines:
        raise ValueError("config.txt contains no [Machine_N] sections.")

    refresh_interval = int(cfg.get("Global", "Refresh_Interval", fallback="3"))
    return AppConfig(machines=machines, refresh_interval=refresh_interval)
