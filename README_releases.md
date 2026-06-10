# DataClarify — Machine Downtime Tracker

> Real-time downtime monitoring for factory floors.  
> Connects directly to Keyence IO-Link Masters via Modbus TCP.  
> No cloud. No subscription. No IT setup required.

---

## Download

| Version | Platform | File |
|---|---|---|
| v1.1 (latest) | Windows 10 / 11 (64-bit) | [DataClarify-v1.1-setup.exe](https://github.com/barneymc/DataClarify/releases/latest/download/DataClarify-v1.1-setup.exe) |

> **Note:** Windows SmartScreen may show a warning on first launch.  
> Click **More info → Run anyway**. The application is safe — it has not yet accumulated enough download history for automatic SmartScreen trust.

---

## What It Does

DataClarify monitors production lines in real time and automatically logs downtime events the moment a machine stops producing. Operators can add comments and categories to each event and export shift reports to CSV — all from a browser on any PC on the same network.

- **Dual machine monitoring** — two independent status tiles, one per IO-Link Master
- **Automatic downtime detection** — configurable threshold per machine
- **Product counter** — rising-edge count per machine, resettable per shift
- **Retrospective commenting** — operators categorise and annotate events after the fact
- **CSV export** — scoped to machine and date range, ready for Excel or Power BI
- **Demo mode** — synthetic data generation for sales demonstrations without hardware
- **Network access** — any PC on the same LAN can open the dashboard; no software install required on those machines

---

## Quick Start

1. Run **DataClarify-v1.1-setup.exe** and follow the installer prompts
2. Open your configuration file — in File Explorer, paste this into the address bar and press Enter:
   ```
   %APPDATA%\DataClarify
   ```
   Then open `config.txt` with Notepad.
3. Set your machine's IP address and IO-Link port number, for example:
   ```ini
   [Machine_1]
   IP           = 192.168.1.30
   Machine_Name = Packaging Line 1
   Port         = 2
   ```
4. Double-click **DataClarify.exe** — the dashboard opens automatically in your browser

The application binds to `http://localhost:8501`. Other devices on the same network can reach it at `http://<your-pc-ip>:8501`.

---

## System Requirements

| Requirement | Detail |
|---|---|
| Operating System | Windows 10 or Windows 11 (64-bit) |
| Network | TCP access to Keyence IO-Link Master on port 502 |
| Port | 8501 must be available on the host PC |
| Hardware | Keyence NQ-MP8L or NQ-EP4L IO-Link Master |
| Browser | Any modern browser (Chrome, Edge, Firefox) |

No Python, no Docker, no additional software required.

---

## Configuration Reference

Edit `%APPDATA%\DataClarify\config.txt` with any text editor (Notepad works fine).

| Parameter | Description | Example |
|---|---|---|
| `IP` | IP address of the Keyence IO-Link Master | `192.168.1.30` |
| `Machine_Name` | Display name shown in the dashboard | `Packaging Line 1` |
| `Port` | Physical IO-Link port number on the master (1–4) | `2` |
| `Rest_Distance` | Detection threshold — product present when reading ≥ this value | `100` |
| `Downtime_Threshold` | Seconds without a product before a downtime event is logged | `10` |
| `Live` | `True` to enable this machine; `False` to hide it | `True` |
| `Refresh_Interval` | Dashboard auto-refresh interval in seconds (under `[Global]`) | `3` |

The Modbus register address is derived automatically from the port number using the Keyence NQ-MP8L/EP4L register map — no manual register lookup required.

---

## Data Storage

All data is stored locally on the host PC. Nothing is sent to the cloud.

| File | Location |
|---|---|
| Configuration | `%APPDATA%\DataClarify\config.txt` |
| Event database | `%APPDATA%\DataClarify\tracker.db` |

The database is a standard SQLite file and can be opened with any SQLite browser if needed.

---

## Uninstalling

Use **Add or Remove Programs** in Windows Settings. Your configuration and event history in `%APPDATA%\DataClarify\` are preserved — remove that folder manually if you want a clean uninstall.

---

## Support

**[dataclarify.io](https://dataclarify.io)**

For installation issues, configuration help, or hardware compatibility questions, visit the website or use the built-in **Run Diagnostics** button in the application sidebar to generate a support report.
