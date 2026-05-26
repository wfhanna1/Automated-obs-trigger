"""
cancel_sb_messages.py

One-shot script to cancel specific scheduled messages in the obs-jobs
Service Bus queue.  Peeks all scheduled messages, matches by server_id
and (optionally) title, then cancels by sequence number.

Usage:
    SERVICE_BUS_CONNECTION="<conn-str>" python3 scripts/cancel_sb_messages.py

Set MATCH_SERVER_ID and MATCH_TITLE below (or pass via env vars) to target
a different event.
"""

import json
import logging
import os
import sys

from azure.servicebus import ServiceBusClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

QUEUE_NAME = "obs-jobs"
MATCH_SERVER_ID = os.environ.get("MATCH_SERVER_ID", "win-server-1")
MATCH_TITLE = os.environ.get(
    "MATCH_TITLE", "English Bible Study and Fellowship Meeting"
)


def main() -> None:
    conn_str = os.environ.get("SERVICE_BUS_CONNECTION")
    if not conn_str:
        logger.error("SERVICE_BUS_CONNECTION environment variable is not set.")
        sys.exit(1)

    logger.info(
        "Peeking %s queue for server_id=%r title=%r ...",
        QUEUE_NAME,
        MATCH_SERVER_ID,
        MATCH_TITLE,
    )

    to_cancel: list[int] = []

    with ServiceBusClient.from_connection_string(conn_str) as client:
        with client.get_queue_receiver(QUEUE_NAME) as receiver:
            # Peek up to 1000 scheduled messages from the start of the queue.
            messages = receiver.peek_messages(max_message_count=1000, sequence_number=1)
            logger.info("Peeked %d message(s).", len(messages))

            for msg in messages:
                try:
                    body = b"".join(msg.body).decode("utf-8")
                    payload = json.loads(body)
                except Exception as exc:
                    logger.warning("Could not decode message seq=%s: %s", msg.sequence_number, exc)
                    continue

                if (
                    payload.get("server_id") == MATCH_SERVER_ID
                    and payload.get("title") == MATCH_TITLE
                    and msg.sequence_number is not None
                ):
                    logger.info(
                        "Matched: seq=%s command=%s scheduled_at=%s",
                        msg.sequence_number,
                        payload.get("command"),
                        msg.scheduled_enqueue_time_utc,
                    )
                    to_cancel.append(msg.sequence_number)

        if not to_cancel:
            logger.info("No matching messages found. Nothing to cancel.")
            return

        logger.info("Cancelling %d message(s): sequence numbers %s", len(to_cancel), to_cancel)
        with client.get_queue_sender(QUEUE_NAME) as sender:
            sender.cancel_scheduled_messages(to_cancel)

    logger.info("Done. %d message(s) cancelled.", len(to_cancel))


if __name__ == "__main__":
    main()
