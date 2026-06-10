import time
from datetime import date

import pandas as pd
import streamlit as st

import db
import demo as demo_mod
import poller as poller_mod
import shared_state
from config import AppConfig, load_config
from diagnose import run_diagnostics

st.set_page_config(
    page_title="DataClarify.io | Downtime Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _init() -> AppConfig:
    cfg = load_config()
    db.init_db()
    for i, machine in enumerate(cfg.machines):
        if machine.live:
            poller_mod.start_poller_thread(machine)
            demo_mod.start_demo_thread(machine, offset=float(i * 4))
    return cfg


try:
    config = _init()
except FileNotFoundError as exc:
    st.error(f"**config.txt not found.** Place config.txt in the same folder as the application.\n\n`{exc}`")
    st.stop()
except Exception as exc:
    st.error(f"**Configuration error:** {exc}")
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    demo_on = st.toggle("Demo Mode", value=shared_state.get_demo_mode())
    shared_state.set_demo_mode(demo_on)
    if demo_on:
        st.warning("DEMO DATA — not live sensor data")

    st.divider()
    if st.button("🔧 Run Diagnostics", width="stretch"):
        with st.spinner("Testing connections…"):
            st.session_state["_diag_result"] = run_diagnostics(
                [m for m in config.machines if m.live]
            )


# ── Deferred toast (must fire on the rerun AFTER Save, not before st.rerun()) ──
if "_pending_toast" in st.session_state:
    st.toast(st.session_state.pop("_pending_toast"), icon="✅")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## [DataClarify.io](https://dataclarify.io) — Machine Downtime Tracker")
st.divider()


# ── Status Tiles ──────────────────────────────────────────────────────────────
live_machines = [m for m in config.machines if m.live]
machine_states = shared_state.get_all()
tile_cols = st.columns(len(live_machines))

for col, machine in zip(tile_cols, live_machines):
    info = machine_states.get(machine.machine_id, {})
    status = info.get("status", "DISCONNECTED")
    with col:
        if status == "RUNNING":
            st.success(f"**{machine.machine_name}**\n\n● RUNNING")
        elif status == "DOWNTIME":
            st.error(f"**{machine.machine_name}**\n\n● DOWN")
        else:
            st.warning(
                f"**{machine.machine_name}**\n\n"
                f"⚠ DISCONNECTED\n\n"
                f"`{machine.ip}:502` unreachable  \n"
                f"[Support: dataclarify.io](https://dataclarify.io)"
            )
        count = shared_state.get_counter(machine.machine_id)
        cnt_col, rst_col = st.columns([3, 1])
        with cnt_col:
            st.markdown(f"**Products: {count}**")
        with rst_col:
            if st.button("Reset", key=f"reset_{machine.machine_id}"):
                shared_state.reset_counter(machine.machine_id)
                st.rerun()

st.divider()


# ── Machine Selector ──────────────────────────────────────────────────────────
name_to_machine = {m.machine_name: m for m in live_machines}
selected_name = st.selectbox("View machine:", list(name_to_machine.keys()))
selected_machine = name_to_machine[selected_name]


# ── Date Range ────────────────────────────────────────────────────────────────
date_col, export_col = st.columns([3, 1])
with date_col:
    date_range = st.date_input("Date range:", value=(date.today(), date.today()))

if isinstance(date_range, (list, tuple)):
    start_date = date_range[0] if len(date_range) > 0 else date.today()
    end_date = date_range[1] if len(date_range) == 2 else start_date
else:
    start_date = end_date = date_range

events = db.get_events(selected_machine.machine_id, start_date=start_date, end_date=end_date)


# ── CSV Export ────────────────────────────────────────────────────────────────
with export_col:
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if events:
        csv_df = pd.DataFrame(events)
        csv_df.insert(0, "Machine_Name", selected_machine.machine_name)
        csv_df["startTime"] = csv_df["startTime"].apply(
            lambda v: pd.to_datetime(v, utc=True).strftime("%Y-%m-%d %H:%M:%S") if pd.notna(v) else ""
        )
        csv_df["endTime"] = csv_df["endTime"].apply(
            lambda v: pd.to_datetime(v, utc=True).strftime("%Y-%m-%d %H:%M:%S") if pd.notna(v) else "Active"
        )
        csv_df["duration"] = csv_df["duration"].apply(
            lambda v: f"{float(v):.1f}s" if pd.notna(v) else "Active"
        )
        st.download_button(
            "Export to CSV",
            data=csv_df.to_csv(index=False).encode(),
            file_name=f"{selected_machine.machine_name}_{selected_machine.machine_id}_{start_date}_{end_date}.csv",
            mime="text/csv",
        )
    else:
        st.button("Export to CSV", disabled=True)


# ── Event Table ───────────────────────────────────────────────────────────────
st.markdown(f"### Downtime Events — {selected_name}")

if events:
    df = pd.DataFrame(events)

    def _fmt_duration(val):
        if pd.isna(val):
            return "Active"
        return f"{float(val):.1f}s"

    def _fmt_ts(val):
        if not val:
            return "Active"
        try:
            return pd.to_datetime(val, utc=True).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(val)[:19]  # trim to seconds if parse fails

    df["startTime"] = df["startTime"].apply(_fmt_ts)
    df["endTime"] = df["endTime"].apply(_fmt_ts)
    df["duration"] = df["duration"].apply(_fmt_duration)
    display_df = df.rename(columns={
        "id": "ID", "startTime": "Start", "endTime": "End",
        "duration": "Duration", "category": "Category", "OperatorComment": "Comment",
    })

    # table_ver increments on Save so the widget re-mounts with no row selected
    table_ver = st.session_state.get("table_ver", 0)
    table_state = st.dataframe(
        display_df[["ID", "Start", "End", "Duration", "Category", "Comment"]],
        width="stretch",
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key=f"event_table_{table_ver}",
        height=215,  # ~5 rows visible; scrollable for older events
    )

    # Resolve selected event: row click takes priority, session state persists across refresh
    selected_rows = table_state.selection.rows
    if selected_rows:
        st.session_state["edit_event_id"] = int(display_df.iloc[selected_rows[0]]["ID"])

    edit_id = st.session_state.get("edit_event_id")
    edit_event = next((e for e in events if e["id"] == edit_id), None)

    # ── Edit Form ─────────────────────────────────────────────────────────────
    expander_label = (
        f"✏️ Editing Event #{edit_id} — {_fmt_ts(edit_event['startTime'])}"
        if edit_event
        else "Edit Event Comment"
    )
    with st.expander(expander_label, expanded=(edit_event is not None)):
        if edit_event:
            categories = db.get_categories()
            cat_labels = ["— none —"] + [c["label"] for c in categories]
            cat_id_map = {c["label"]: c["id"] for c in categories}
            existing_cat = edit_event.get("category")
            default_cat_idx = cat_labels.index(existing_cat) if existing_cat in cat_labels else 0

            with st.form(f"edit_form_{edit_id}"):
                new_cat = st.selectbox("Category:", cat_labels, index=default_cat_idx)
                new_comment = st.text_input(
                    "Comment:", value=edit_event.get("OperatorComment") or ""
                )
                if st.form_submit_button("Save"):
                    db.update_event_comment(edit_id, new_comment, cat_id_map.get(new_cat))
                    st.session_state["_pending_toast"] = f"Event #{edit_id} updated."
                    st.session_state.pop("edit_event_id", None)
                    st.session_state["table_ver"] = table_ver + 1  # deselect row
                    st.rerun()
        else:
            st.caption("Click a row in the table above to edit its comment and category.")

else:
    st.info("No downtime events recorded for this period.")


# ── Diagnostics Result ────────────────────────────────────────────────────────
if "_diag_result" in st.session_state:
    st.divider()
    diag_title_col, diag_close_col = st.columns([9, 1])
    with diag_title_col:
        st.markdown("### 🔧 Diagnostics")
    with diag_close_col:
        if st.button("✕ Close", key="close_diag"):
            del st.session_state["_diag_result"]
            st.rerun()
    st.caption("Copy the output below to share with support.")
    st.code(st.session_state["_diag_result"], language=None)


# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(config.refresh_interval)
st.rerun()
