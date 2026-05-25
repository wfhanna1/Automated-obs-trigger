"""
queue_manager.py

Helpers for managing the obs-jobs Service Bus queue.
"""

from __future__ import annotations

from azure.servicebus import ServiceBusClient


PEEK_BATCH_SIZE = 1000


def purge_scheduled_messages(client: ServiceBusClient, queue_name: str) -> int:
    """Cancel every scheduled message in the queue. Returns the count cancelled."""
    with client.get_queue_receiver(queue_name) as receiver:
        messages = receiver.peek_messages(
            max_message_count=PEEK_BATCH_SIZE, sequence_number=1,
        )
        sequence_numbers = [m.sequence_number for m in messages if m.sequence_number is not None]
    if not sequence_numbers:
        return 0
    with client.get_queue_sender(queue_name) as sender:
        sender.cancel_scheduled_messages(sequence_numbers)
    return len(sequence_numbers)
