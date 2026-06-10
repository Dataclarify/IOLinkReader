"""
Standalone connectivity diagnostic — run this directly:
    python diagnose.py

Tests TCP reachability on port 502 and then attempts a Modbus read,
so you can see exactly where a connection problem lies.
"""
import contextlib
import io
import socket
import struct
import sys

from config import load_config, MachineConfig

TCP_TIMEOUT = 5


def test_tcp(ip: str, port: int = 502) -> bool:
    print(f"\n[1] TCP socket test → {ip}:{port}")
    try:
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT):
            print(f"    ✓ Port {port} is open and accepting connections")
            return True
    except ConnectionRefusedError:
        print(f"    ✗ Connection REFUSED — port {port} is closed on the device")
    except socket.timeout:
        print(f"    ✗ TIMEOUT after {TCP_TIMEOUT}s — host reachable via ping but port {port} is not responding")
        print(f"      → Check if Modbus TCP is enabled in the Keyence device web interface")
    except OSError as exc:
        print(f"    ✗ OS error: {exc}")
    return False


def test_modbus(ip: str, register: int) -> None:
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        print("    pymodbus not installed — run: pip install pymodbus")
        return

    print(f"\n[2] Modbus TCP read → {ip}:502  register={register}")
    client = ModbusTcpClient(ip, port=502, timeout=TCP_TIMEOUT)
    try:
        if not client.connect():
            print("    ✗ pymodbus could not connect")
            return
        print("    ✓ pymodbus connected")

        result = client.read_holding_registers(address=register, count=1)
        if result.isError():
            print(f"    ✗ Modbus error response: {result}")
            print(f"      → Device connected but register {register} may be wrong, or Modbus not fully configured")
        else:
            raw = result.registers[0]
            signed = struct.unpack(">h", struct.pack(">H", raw))[0]
            distance = signed >> 4
            print(f"    ✓ Register read OK")
            print(f"      raw={raw}  signed={signed}  distance (after >>4)={distance}")
    finally:
        client.close()


def run_diagnostics(machines: list[MachineConfig]) -> str:
    """Run all connectivity tests and return the output as a string.
    Called by the Streamlit UI; also used by main() for CLI output."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for machine in machines:
            if not machine.live:
                print(f"\n--- {machine.machine_name} ({machine.machine_id}) [Live=False — skipped] ---")
                continue

            print(f"\n{'='*60}")
            print(f"  {machine.machine_name}  ({machine.machine_id})")
            print(f"  IP={machine.ip}  Port={machine.port}  Register={machine.register_start}")
            print(f"  Rest_Distance={machine.rest_distance}  Downtime_Threshold={machine.downtime_threshold}s")
            print(f"{'='*60}")

            if test_tcp(machine.ip):
                test_modbus(machine.ip, machine.register_start)

        print("\nDone.")
    return buf.getvalue()


def main() -> None:
    try:
        cfg = load_config()
    except Exception as exc:
        print(f"Could not load config.txt: {exc}")
        sys.exit(1)
    print(run_diagnostics(cfg.machines))


if __name__ == "__main__":
    main()
