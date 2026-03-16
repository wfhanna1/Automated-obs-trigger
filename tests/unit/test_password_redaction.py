"""
tests/unit/test_password_redaction.py

Unit tests for OBS WebSocket password redaction in log output.

The obsws_python library logs connection parameters including the password
in plaintext. Our PasswordRedactionFilter must scrub these before they
reach Application Insights.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from obs_websocket import PasswordRedactionFilter


# ---------------------------------------------------------------------------
# PasswordRedactionFilter unit tests
# ---------------------------------------------------------------------------

class TestPasswordRedactionFilter:

    def test_redacts_password_in_message_string(self):
        """password='secret123' should become password='***'."""
        filt = PasswordRedactionFilter()
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting with parameters: host='localhost' port=4455 password='MySecret' subs=0 timeout=10",
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert "MySecret" not in record.msg
        assert "password='***'" in record.msg

    def test_preserves_non_password_content(self):
        """Other parts of the message should remain intact."""
        filt = PasswordRedactionFilter()
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting with parameters: host='localhost' port=4455 password='secret' subs=0 timeout=10",
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert "host='localhost'" in record.msg
        assert "port=4455" in record.msg
        assert "subs=0" in record.msg
        assert "timeout=10" in record.msg

    def test_leaves_messages_without_password_unchanged(self):
        """Messages that don't contain password= should pass through unmodified."""
        filt = PasswordRedactionFilter()
        original = "Successfully identified ReqClient with the server using RPC version:1"
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=original,
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert record.msg == original

    def test_filter_always_returns_true(self):
        """The filter should never suppress records, only redact them."""
        filt = PasswordRedactionFilter()
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="password='secret'",
            args=None,
            exc_info=None,
        )
        result = filt.filter(record)
        assert result is True

    def test_redacts_password_with_double_quotes(self):
        """password=\"secret\" should also be redacted."""
        filt = PasswordRedactionFilter()
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='Connecting with parameters: host="localhost" port=4455 password="TopSecret" subs=0',
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert "TopSecret" not in record.msg
        assert 'password="***"' in record.msg

    def test_redacts_password_with_special_characters(self):
        """Passwords with special regex chars should be handled safely."""
        filt = PasswordRedactionFilter()
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="password='p@ss$w0rd!#'",
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert "p@ss$w0rd!#" not in record.msg
        assert "password='***'" in record.msg

    def test_redacts_empty_password(self):
        """An empty password should also be redacted."""
        filt = PasswordRedactionFilter()
        record = logging.LogRecord(
            name="obsws_python.baseclient",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="password=''",
            args=None,
            exc_info=None,
        )
        filt.filter(record)
        assert "password='***'" in record.msg


# ---------------------------------------------------------------------------
# Integration: filter is installed on the obsws_python logger
# ---------------------------------------------------------------------------

class TestFilterInstallation:

    def test_obsws_python_logger_has_redaction_filter(self):
        """The obsws_python logger must have PasswordRedactionFilter installed."""
        obs_logger = logging.getLogger("obsws_python")
        filter_types = [type(f) for f in obs_logger.filters]
        assert PasswordRedactionFilter in filter_types
