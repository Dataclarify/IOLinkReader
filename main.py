"""
Entry point for the PyInstaller .exe build.
Launches the Streamlit server bound to all interfaces (0.0.0.0) and
opens the local browser automatically.

Development: run `streamlit run app.py` directly instead.
"""
import os
import socket
import sys
import threading
import time
import webbrowser


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def _open_browser(delay: float = 4.0) -> None:
    time.sleep(delay)
    webbrowser.open("http://localhost:8501")


def main() -> None:
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    app_path = os.path.join(base_path, "app.py")
    local_ip = _get_local_ip()

    print("=" * 60)
    print("  DataClarify.io — Machine Downtime Tracker")
    print("=" * 60)
    print(f"  Local:   http://localhost:8501")
    print(f"  Network: http://{local_ip}:8501")
    print()
    print("  Other devices on your network can open the dashboard")
    print(f"  at http://{local_ip}:8501")
    print()
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)

    threading.Thread(target=_open_browser, daemon=True).start()

    # Override any user-level Streamlit config that conflicts with bundled deployment
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port=8501",
        "--server.address=0.0.0.0",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
