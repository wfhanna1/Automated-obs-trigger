"""
validate_sb_messages.py

Compare scheduled Service Bus messages in obs-jobs against the current
schedule CSV on GitHub.  Reports:

  - Expected messages with no matching queue entry  (missing)
  - Queue entries with no matching schedule row     (orphans / duplicates)
  - Duplicate matches                                (same (server_id, command,
                                                      scheduled_at) appears more
                                                      than once)
"""

import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime

import pytz
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from schedule_loader import load_schedule  # noqa: E402

from azure.servicebus import ServiceBusClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("uamqp").setLevel(logging.WARNING)

QUEUE_NAME = "obs-jobs"
CSV_URL = (
    "https://raw.githubusercontent.com/wfhanna1/Automated-obs-trigger/"
    "main/schedules/current_week.csv"
)


def expected_messages() -> list[dict]:
    csv_text = requests.get(CSV_URL, timeout=15).text
    entries = load_schedule(csv_text)
    expected = []
    for e in entries:
        for command, when in [("start", e.start_dt), ("stop", e.stop_dt)]:
            expected.append({
                "server_id": e.server_id,
                "command": command,
                "action": e.action,
                "title": e.title,
                "scheduled_at": when.astimezone(pytz.utc).replace(microsecond=0),
            })
    return expected


def queue_messages(conn_str: str) -> list[dict]:
    out = []
    with ServiceBusClient.from_connection_string(conn_str) as client:
        with client.get_queue_receiver(QUEUE_NAME) as receiver:
            msgs = receiver.peek_messages(max_message_count=1000, sequence_number=1)
            for m in msgs:
                try:
                    body = b"".join(m.body).decode("utf-8")
                    payload = json.loads(body)
                except Exception:
                    continue
                out.append({
                    "seq": m.sequence_number,
                    "server_id": payload.get("server_id"),
                    "command": payload.get("command"),
                    "action": payload.get("action"),
                    "title": payload.get("title"),
                    "scheduled_at": m.scheduled_enqueue_time_utc.replace(
                        tzinfo=pytz.utc, microsecond=0
                    ) if m.scheduled_enqueue_time_utc else None,
                })
    return out


def key(d: dict) -> tuple:
    return (d["server_id"], d["command"], d["action"], d["scheduled_at"])


def main() -> int:
    conn_str = os.environ.get("SERVICE_BUS_CONNECTION")
    if not conn_str:
        logger.error("SERVICE_BUS_CONNECTION not set.")
        return 1

    now_utc = datetime.now(tz=pytz.utc).replace(microsecond=0)
    expected = expected_messages()
    actual = queue_messages(conn_str)

    # Filter out queue messages whose scheduled time is in the past
    # (load_schedule already filters past sessions out of `expected`).
    actual_future = [a for a in actual if a["scheduled_at"] and a["scheduled_at"] > now_utc]
    actual_past = [a for a in actual if a not in actual_future]

    expected_keys = Counter(key(e) for e in expected)
    actual_keys = Counter(key(a) for a in actual_future)

    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys

    # Duplicates: present multiple times in queue but expected once or fewer
    duplicates = {k: actual_keys[k] for k in actual_keys if actual_keys[k] > expected_keys.get(k, 0)}

    print("\n=== Schedule validation ===")
    print(f"Current time (UTC):           {now_utc}")
    print(f"Expected future messages:     {len(expected)}")
    print(f"Queue messages (total peeked):{len(actual)}")
    print(f"Queue messages (future only): {len(actual_future)}")
    if actual_past:
        print(f"Queue messages (past, will be ignored by check): {len(actual_past)}")

    ok = True

    if missing:
        ok = False
        print(f"\nMISSING ({sum(missing.values())}) — expected but not in queue:")
        for k, count in missing.items():
            sid, cmd, act, when = k
            print(f"  x{count}  {sid:14}  {cmd:5}  {act:9}  {when}")

    if extra:
        ok = False
        print(f"\nEXTRA ({sum(extra.values())}) — in queue but not in current schedule:")
        for k, count in extra.items():
            sid, cmd, act, when = k
            # Find seq numbers
            seqs = [a["seq"] for a in actual_future if key(a) == k]
            seqs_str = ",".join(str(s) for s in seqs[:count])
            print(f"  x{count}  {sid:14}  {cmd:5}  {act:9}  {when}  seq={seqs_str}")

    if duplicates:
        ok = False
        print("\nDUPLICATES — same (server, command, time) enqueued more than expected:")
        for k, count in duplicates.items():
            sid, cmd, act, when = k
            seqs = [a["seq"] for a in actual_future if key(a) == k]
            print(f"  {sid:14}  {cmd:5}  {act:9}  {when}  count={count}  seqs={seqs}")

    if ok:
        print("\nOK — queue matches the current schedule exactly.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
