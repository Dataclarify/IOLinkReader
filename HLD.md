# High-Level Design: MOP Machine Downtime Tracker

## 1. Architecture Overview

Single-process, standalone Windows executable built with **PyInstaller**. All components run inside one Python process — no Docker, no services, no installer required. Two independent poller threads run concurrently, one per IO-Link Master.

```
DataClarify.exe
│
├── Streamlit Server (main thread)          ← browser UI on 0.0.0.0:8501
│      └── auto-rerun every Refresh_Interval seconds (from [Global])
│
├── Poller Thread — Machine_1               ← background daemon thread
│      ├── [Live]  Modbus TCP → 192.168.1.30:502
│      └── [Demo]  synthetic event generator
│
├── Poller Thread — Machine_2               ← background daemon thread
│      ├── [Live]  Modbus TCP → 192.168.0.51:502
│      └── [Demo]  synthetic event generator
│
├── State Machine (one instance per machine, shared in-process)
│      RUNNING ──► DOWNTIME ──► RUNNING
│           └──► DISCONNECTED
│
└── SQLite Database (local file, shared)
       ├── DowntimeEvent    (Machine_ID column separates the two machines)
       └── DowntimeCategory
```

**Thread coordination:** each poller thread writes to SQLite independently using WAL journal mode, which allows concurrent writes without blocking the Streamlit read path.

---

## 2. Component Breakdown

| Component | Responsibility | Key Library |
|---|---|---|
| `main.py` | PyInstaller entry point; detects local IP, opens browser, launches Streamlit on 0.0.0.0 | `threading`, `webbrowser` |
| `config.py` | Parses INI-format `config.txt`; derives register address from Port; returns list of `MachineConfig` objects | `configparser` |
| `poller.py` | Modbus TCP polling loop, state machine, rising-edge counter, event persistence — one instance per machine | `pymodbus` |
| `demo.py` | Synthetic event generator; mirrors the poller interface, used when Demo Mode is on | `random`, `time` |
| `db.py` | SQLite schema init, CRUD helpers | `sqlite3` |
| `app.py` | Streamlit UI — dual tiles with product counters, machine dropdown, event table, comments, CSV export, diagnostics panel | `streamlit`, `pandas` |
| `diagnose.py` | TCP + Modbus connectivity test; callable from UI (returns string) or CLI | `socket`, `pymodbus` |
| `shared_state.py` | Thread-safe module-level singleton; stores machine status, distance, and product counters | `threading` |

---

## 3. Configuration (`config.txt`)

```ini
# Port selects the IO-Link port on the Keyence NQ-MP8L/EP4L master.
# Register address is derived automatically: Port 1=2, Port 2=18, Port 3=34, Port 4=50
# Override with Register_Start = <n> only if using a non-standard register.

[Machine_1]
IP                 = 192.168.1.30
Machine_ID         = Machine_01
Machine_Name       = Packaging Line 1
Port               = 2          # IO-Link port on master → Modbus register 18
Rest_Distance      = 100
Downtime_Threshold = 10
Live               = True

[Machine_2]
IP                 = 192.168.0.51
Machine_ID         = Machine_02
Machine_Name       = Filling Station B
Port               = 3          # IO-Link port on master → Modbus register 34
Rest_Distance      = 100
Downtime_Threshold = 20
Live               = False

[Global]
Refresh_Interval   = 3
```

**Port → Register derivation** (Keyence NQ-MP8L/EP4L register map):

| Port | Register |
|---|---|
| 1 | 2 |
| 2 | 18 |
| 3 | 34 |
| 4 | 50 |

Formula: `register = 2 + (port - 1) × 16`

`Register_Start` can be added as an explicit override for non-standard hardware. If omitted, the register is calculated automatically from `Port`.

`config.py` reads all `[Machine_*]` sections dynamically — adding a third machine requires only a new config section, no code changes. Inline `#` comments in config.txt are supported.

---

## 4. Data Model

```sql
CREATE TABLE DowntimeEvent (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    startTime        TIMESTAMP NOT NULL,   -- ISO-8601, UTC
    endTime          TIMESTAMP,            -- NULL while event is active
    duration         REAL,                 -- seconds, calculated on endTime write
    Machine_ID       TEXT NOT NULL,        -- from config [Machine_N] section
    OperatorComment  TEXT,
    category_id      INTEGER REFERENCES DowntimeCategory(id)
);

CREATE TABLE DowntimeCategory (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL UNIQUE
);
```

Both machines write to the same `DowntimeEvent` table. `Machine_ID` is the discriminator for all queries and exports. `PRAGMA journal_mode=WAL` is set on startup to allow concurrent reads and writes across threads.

### Modbus Read & Data Transformation

```python
import struct
from pymodbus.client import ModbusTcpClient

def read_distance(client: ModbusTcpClient, register_start: int) -> int:
    result = client.read_holding_registers(address=register_start, count=1)
    raw = result.registers[0]                                    # unsigned 16-bit
    signed = struct.unpack('>h', struct.pack('>H', raw))[0]      # signed 16-bit BE
    return signed >> 4                                           # strip lower 4 flag bits
```

This is the direct Python equivalent of the Node-RED reference implementation:
```javascript
const buf = Buffer.from([msg.payload.buffer[36], msg.payload.buffer[37]]);
const currentDistance = buf.readInt16BE() >> 4;
```

The returned integer is compared against `Rest_Distance` to determine product presence.

---

## 5. State Machine (per machine)

```
          first successful read
DISCONNECTED ──────────────────────────────────────► RUNNING
                                                         │
          no product for > Downtime_Threshold            │
RUNNING ─────────────────────────────────────────► DOWNTIME
   ▲                                                     │
   │            product present again                    │
   └─────────────────────────────────────────────────────┘
   │
   └──── TCP :502 unreachable ──► DISCONNECTED
```

Key behaviours:
- DISCONNECTED → RUNNING transitions on the **first successful register read**, regardless of whether a product is present. This prevents false downtime events immediately after reconnect.
- The product counter uses **rising-edge detection** — it increments only on the False→True transition of `product_present`, so a stationary product counts as one regardless of poll cycles.
- On entering DISCONNECTED, any open downtime event is closed with the current timestamp.

| From | Trigger | To | DB Action |
|---|---|---|---|
| DISCONNECTED | First successful read | RUNNING | — |
| RUNNING | No product for > `Downtime_Threshold` s | DOWNTIME | INSERT DowntimeEvent (startTime) |
| DOWNTIME | Product detected | RUNNING | UPDATE DowntimeEvent SET endTime, duration |
| RUNNING / DOWNTIME | TCP :502 unreachable | DISCONNECTED | Close open event if any |

---

## 6. UI Layout (`app.py`)

```
┌─ Sidebar ──────────────────────────────┐
│  [■] Demo Mode  ← st.toggle()          │
│  ⚠  DEMO DATA — not live  (banner)     │
│  ────────────────────────────────────  │
│  [🔧 Run Diagnostics]                  │
│  [Clear]                               │
└────────────────────────────────────────┘

┌─ Main ──────────────────────────────────────────────────────────────┐
│                                                                     │
│   ## [DataClarify.io](https://dataclarify.io)                       │
│   — Machine Downtime Tracker                                        │
│                                                                     │
│   ┌──────────────────────────┐   ┌──────────────────────────┐       │
│   │  Packaging Line 1        │   │  Filling Station B       │       │
│   │  ● RUNNING               │   │  ● DOWN                  │       │
│   │  Products: 42  [Reset]   │   │  Products: 17  [Reset]   │       │
│   └──────────────────────────┘   └──────────────────────────┘       │
│                                                                     │
│   View machine:  [ Packaging Line 1 ▼ ]                             │
│                                                                     │
│   Date range: [ 2026-06-07 — 2026-06-07 ]    [Export to CSV]       │
│                                                                     │
│   ### Downtime Events — Packaging Line 1                            │
│   ┌────┬─────────────────────┬──────────┬──────────┬──────────┐    │
│   │ ID │ Start               │ End      │ Duration │ Category │    │
│   ├────┼─────────────────────┼──────────┼──────────┼──────────┤    │
│   │  5 │ 2026-06-07 12:22:13 │ Active   │ Active   │          │    │
│   │  4 │ 2026-06-07 12:19:51 │ 12:20:14 │ 23.0s    │          │    │
│   └────┴─────────────────────┴──────────┴──────────┴──────────┘    │
│                                                                     │
│   ▶ ✏️ Editing Event #4 — 2026-06-07 12:19:51  (expander)          │
│     Category: [ — none — ▼ ]                                        │
│     Comment:  [___________________________]                         │
│     [Save]                                                          │
│                                                                     │
│   ── (diagnostics panel, shown only after Run Diagnostics) ──      │
│   ### 🔧 Diagnostics                                                │
│   Copy the output below to share with support.                      │
│   ┌─────────────────────────────────────────────────────────┐      │
│   │ === Packaging Line 1 ===                                 │      │
│   │ [1] TCP socket test → 192.168.1.30:502 ✓                │      │
│   │ [2] Modbus TCP read  raw=2145 dist=134  ✓               │      │
│   └─────────────────────────────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Key UI patterns:**
- Product counter uses `shared_state.get_counter(machine_id)`; Reset button calls `shared_state.reset_counter()` + `st.rerun()`
- Row selection uses `selection_mode="single-row"` on `st.dataframe`. A versioned key (`event_table_{table_ver}`) forces the dataframe to remount with no selection after a Save, clearing the edit form
- Edit form key includes the event ID (`edit_form_{edit_id}`) so switching between events remounts the form with fresh field values
- Toast notification on Save uses a deferred pattern: store message in `st.session_state["_pending_toast"]`, fire `st.toast()` at the top of the next rerun (calling it before `st.rerun()` discards it)
- Diagnostics panel is stored in `st.session_state["_diag_result"]`; only rendered when that key exists

---

## 7. Auto-Refresh Strategy

```python
# app.py — bottom of script
import time
time.sleep(config.refresh_interval)
st.rerun()
```

On each rerun, Streamlit re-reads the machine-state dict (updated by poller threads) and re-queries SQLite. `Refresh_Interval` is configurable in `config.txt` under `[Global]`.

---

## 8. Demo Mode

Toggled via `st.toggle("Demo Mode")` in the sidebar. State held in `shared_state` (thread-safe, not session state) so both background threads see the change immediately.

- **Off:** poller threads run, real Modbus data flows.
- **On:** poller threads sleep; `demo.py` generator threads produce synthetic production/downtime cycles with a 4-second desync between machines. Rising-edge counter logic matches the live poller exactly.

Debug output is printed to the console in both modes:
```
[12:22:13] Machine_01 | reg=18 raw=2145 dist=134 threshold=100 product=YES state=RUNNING
[12:22:13] DEMO Machine_02 | dist=118 product=YES phase=PROD state=RUNNING
```

---

## 9. Packaging & Distribution

```
build.bat  →  PyInstaller DataClarify.spec  →  dist\DataClarify\  →  DataClarify-v1.0.0.zip
```

PyInstaller flags: `--onedir`, `console=True` (console kept visible — shows IP addresses and poller debug output).

On launch (`main.py`):
1. Detects local network IP via a UDP socket probe
2. Prints local URL and network URL to the console
3. Starts a daemon thread that opens `http://localhost:8501` in the browser after a 4-second delay
4. Sets `STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false` to prevent config conflicts
5. Calls `streamlit.web.cli.main()` with `--server.address=0.0.0.0`

Distribution ZIP structure:
```
DataClarify-v1.0.0.zip
  └── DataClarify\
        ├── DataClarify.exe     ← user double-clicks this
        ├── config.txt          ← user edits with their IP and port
        └── _internal\          ← Python runtime + dependencies (do not modify)
```

The SQLite database (`tracker.db`) is created in `%APPDATA%\DataClarify\tracker.db` on first run and persists across restarts. This location is always writable, including when the exe is installed under `Program Files`.

---

## 10. Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| SQLite write contention between two poller threads | WAL journal mode; each thread opens its own connection per poll cycle |
| One machine offline blocks the other | Threads are fully independent; DISCONNECTED state is per-machine |
| Port 8501 already in use | Documented in README; user can pass `--server.port` on command line |
| Windows Defender SmartScreen blocking unsigned exe | Code signing certificate recommended before public distribution |
| Demo mode left on at site | Sidebar warning banner renders on every rerun; visually prominent |
| config.txt inline comments breaking int() parsing | `configparser` initialised with `inline_comment_prefixes=('#', ';')` |

---

## 11. Post-v1 Roadmap (Not in Scope for Day 1)

The following enhancements are captured here for planning purposes. None are to be implemented in v1. The v1 principle is: bare-bones, stable, shippable on day one.

### 11.1 Uptime % KPI Tile
Display a single large uptime percentage (e.g., "94.2% Uptime") per machine, calculated over a rolling 8-hour window, shown directly beneath or within each status tile. Requires a time-windowed aggregation query over `DowntimeEvent`.

### 11.2 "Last Downtime" Sub-label on Status Tile
When a machine is in the RUNNING state, show a sub-label such as "Last event 18 mins ago — 4 min duration" below the green tile. Sourced from the most recent `endTime` row for that `Machine_ID`. Keeps the tile feeling live and provides context without requiring the operator to scroll the table.

### 11.3 Shift Quick-Select for Export
Replace the raw date-range picker on the CSV export with three quick-select buttons: `Morning`, `Afternoon`, `Night`. Shift start/end times are defined in `config.txt` under `[Global]`. Pre-fills the date range automatically. Plant managers think in shifts, not timestamps — this removes friction from the handover reporting flow.

### 11.4 Context-Aware Demo Machine Names
Before a customer site visit, the field technician updates `Machine_Name` in `config.txt` to match the prospect's actual equipment names (e.g., "Line 3 Filler", "Cap Applicator"). No recompile required. Adds immediate credibility during live demonstrations at zero development cost — purely an operational/sales process.

### 11.5 "Powered by DataClarify.io" Footer
A fixed one-line footer at the bottom of every page: `Powered by DataClarify.io`. Ensures brand presence on any screenshot taken by a customer's IT or operations team during a demo or evaluation period.

### 11.6 Shift Downtime Summary Banner
A single summary metric displayed below the dual status tiles: e.g., "47 min lost today across 2 machines — 6 events." Sourced from a simple aggregation of `duration` and row count in `DowntimeEvent` filtered to the current date. This is the number a production manager walks into their morning meeting with; surfacing it instantly makes the value proposition self-evident.

### 11.7 MCP Server (IO-Link Data for AI Agents)
Wrap the existing Modbus read logic and SQLite queries as a Model Context Protocol (MCP) server, exposing factory floor data to AI assistants such as Claude Desktop.

**Target users:** AI/automation developers, technical system integrators, and the MCP community — a different persona to the plant engineer, but valuable for product-market fit feedback. Technical users articulate what they need precisely; their feature requests and issues will inform the commercial product roadmap.

**Proposed MCP tools:**
- `get_machine_status` — returns current status, distance reading, and product count for one or all machines
- `get_downtime_events` — queries `DowntimeEvent` by machine and date range, returns structured JSON
- `get_config` — returns active machine configuration (names, IPs, thresholds)
- `run_diagnostics` — runs the existing TCP + Modbus connectivity test and returns the result

**Distribution:** published as a separate open-source repo under the `Dataclarify` GitHub org. Free, MIT licensed. Acts as a developer relations channel and drives organic traffic to dataclarify.io.

**When to build:** after v1 has 5–10 active users and the core data model is stable. The Modbus and SQLite logic already exists — wrapping it as MCP tools is approximately one week of work.
