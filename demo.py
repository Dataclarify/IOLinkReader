import random
import threading
import time
from datetime import datetime, timezone, timedelta

import db
import shared_state
from config import MachineConfig


def _run(machine: MachineConfig, initial_offset: float = 0.0) -> None:
    time.sleep(initial_offset)  # desync machines so state changes don't happen in lockstep

    state = "RUNNING"
    last_product_time: datetime | None = None
    open_event_id: int | None = None
    prev_product: bool = False

    # Alternate between production bursts and downtime gaps
    in_production = True
    next_flip = time.time() + random.uniform(20, 60)

    print(f"[DEMO] {machine.machine_id} thread started (offset={initial_offset}s)", flush=True)

    while True:
        if not shared_state.get_demo_mode():
            time.sleep(1)
            continue

        now = datetime.now(timezone.utc)
        now_ts = time.time()

        if now_ts >= next_flip:
            in_production = not in_production
            next_flip = now_ts + (random.uniform(30, 90) if in_production else random.uniform(25, 55))
            phase = "PRODUCTION burst" if in_production else "DOWNTIME gap"
            secs_until = next_flip - now_ts
            print(
                f"[{now.strftime('%H:%M:%S')}] DEMO {machine.machine_id} | "
                f"phase → {phase}  (next flip in {secs_until:.0f}s)",
                flush=True,
            )

        product_present = in_production and (random.random() < 0.85)

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

        # Product present → high reading (above threshold); no product → near-zero reading
        distance = (
            random.randint(machine.rest_distance + 10, machine.rest_distance + 50)
            if product_present
            else random.randint(0, max(0, machine.rest_distance - 20))
        )
        shared_state.update_machine(machine.machine_id, state, distance)
        print(
            f"[{now.strftime('%H:%M:%S')}] DEMO {machine.machine_id} | "
            f"dist={distance} product={'YES' if product_present else 'NO '} "
            f"phase={'PROD' if in_production else 'DOWN'} state={state}",
            flush=True,
        )
        time.sleep(1)


def start_demo_thread(machine: MachineConfig, offset: float = 0.0) -> threading.Thread:
    t = threading.Thread(
        target=_run, args=(machine, offset), daemon=True, name=f"demo-{machine.machine_id}"
    )
    t.start()
    return t
