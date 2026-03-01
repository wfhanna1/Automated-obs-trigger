"""
schedule_loader.py

Parses and validates the weekly OBS schedule CSV.

Expected CSV columns:
    server_id, date, start_time, stop_time, action, timezone

Returns a list of ScheduleEntry objects with timezone-aware datetimes.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"server_id", "date", "start_time", "stop_time", "action", "timezone"}
VALID_ACTIONS = {"recording", "streaming"}


@dataclass
class ScheduleEntry:
    server_id: str
    action: str          # "recording" | "streaming"
    start_dt: datetime   # timezone-aware
    stop_dt: datetime    # timezone-aware


def load_schedule(csv_text: str, known_server_ids: set[str] | None = None) -> list[ScheduleEntry]:
    """
    Parse CSV text and return a list of ScheduleEntry objects.

    Args:
        csv_text:          Raw CSV string (e.g. fetched from GitHub).
        known_server_ids:  Optional set of valid server IDs from servers.yaml.
                           If provided, rows with unknown IDs raise ValueError.

    Returns:
        List of ScheduleEntry with timezone-aware start_dt / stop_dt.
        Rows whose stop_dt is already in the past are silently skipped.

    Raises:
        ValueError: On missing columns, invalid values, or unknown server IDs.
    """
    reader = csv.DictReader(
        line for line in io.StringIO(csv_text) if not line.lstrip().startswith("#")
    )

    if reader.fieldnames is None:
        raise ValueError("CSV is empty or has no header row.")

    actual_columns = {col.strip() for col in reader.fieldnames}
    missing = REQUIRED_COLUMNS - actual_columns
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    entries: list[ScheduleEntry] = []
    now_utc = datetime.now(tz=pytz.utc)

    for row_num, row in enumerate(reader, start=2):
        row = {k.strip(): v.strip() for k, v in row.items()}

        server_id = row["server_id"]
        action = row["action"].lower()
        tz_name = row["timezone"]
        date_str = row["date"]
        start_str = row["start_time"]
        stop_str = row["stop_time"]

        # Validate action
        if action not in VALID_ACTIONS:
            raise ValueError(
                f"Row {row_num}: invalid action '{action}'. Must be one of {VALID_ACTIONS}."
            )

        # Validate timezone
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            raise ValueError(f"Row {row_num}: unknown timezone '{tz_name}'.")

        # Validate server_id
        if known_server_ids is not None and server_id not in known_server_ids:
            raise ValueError(
                f"Row {row_num}: server_id '{server_id}' not found in servers.yaml."
            )

        # Parse datetimes
        try:
            start_naive = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M")
            stop_naive = datetime.strptime(f"{date_str} {stop_str}", "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError(
                f"Row {row_num}: cannot parse date/time — {exc}. "
                "Expected date=YYYY-MM-DD, start_time/stop_time=HH:MM."
            )

        start_dt = tz.localize(start_naive).astimezone(pytz.utc)
        stop_dt = tz.localize(stop_naive).astimezone(pytz.utc)

        if stop_dt <= start_dt:
            raise ValueError(
                f"Row {row_num}: stop_time '{stop_str}' must be after start_time '{start_str}'."
            )

        # Skip sessions that have already ended
        if stop_dt <= now_utc:
            logger.info(
                "Skipping past session: server=%s date=%s start=%s (already ended).",
                server_id, date_str, start_str,
            )
            continue

        entries.append(ScheduleEntry(
            server_id=server_id,
            action=action,
            start_dt=start_dt,
            stop_dt=stop_dt,
        ))

    logger.info("Loaded %d future session(s) from schedule.", len(entries))
    return entries
