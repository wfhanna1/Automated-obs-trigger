"""
tests/unit/test_queue_manager.py

Unit tests for src/queue_manager.py purge_scheduled_messages helper.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


def _wire_client(peeked_seqs: list[int]) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (client, receiver, sender) mocks with context-manager plumbing.

    `peeked_seqs` is the list of sequence numbers the receiver's peek_messages
    call will return (one mock message per seq).
    """
    receiver = MagicMock()
    sender = MagicMock()
    receiver.peek_messages.return_value = [
        MagicMock(sequence_number=s) for s in peeked_seqs
    ]

    client = MagicMock()
    client.get_queue_receiver.return_value.__enter__ = MagicMock(return_value=receiver)
    client.get_queue_receiver.return_value.__exit__ = MagicMock(return_value=False)
    client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=sender)
    client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
    return client, receiver, sender


class TestPurgeScheduledMessages:

    def test_cancels_every_peeked_sequence_number(self):
        from queue_manager import purge_scheduled_messages

        client, _, sender = _wire_client(peeked_seqs=[10, 20, 30])

        count = purge_scheduled_messages(client, "obs-jobs")

        sender.cancel_scheduled_messages.assert_called_once_with([10, 20, 30])
        assert count == 3

    def test_empty_queue_does_not_call_cancel(self):
        from queue_manager import purge_scheduled_messages

        client, _, sender = _wire_client(peeked_seqs=[])

        count = purge_scheduled_messages(client, "obs-jobs")

        sender.cancel_scheduled_messages.assert_not_called()
        assert count == 0
