"""
conftest.py — shared pytest fixtures for all test suites.
"""

import pytest


# ---------------------------------------------------------------------------
# Future date helpers
# ---------------------------------------------------------------------------

# Use a date far in the future so rows are never treated as "past sessions"
FUTURE_DATE = "2099-01-15"
FUTURE_DATE_2 = "2099-01-16"


# ---------------------------------------------------------------------------
# Sample valid CSV text
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_csv_text():
    """Minimal valid CSV with a single future recording session."""
    return (
        "server_id,date,start_time,stop_time,action,timezone\n"
        f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,America/New_York\n"
    )


@pytest.fixture
def multi_row_csv_text():
    """Valid CSV with two future sessions on different servers and timezones."""
    return (
        "server_id,date,start_time,stop_time,action,timezone\n"
        f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,America/New_York\n"
        f"mac-server-1,{FUTURE_DATE_2},14:00,15:30,streaming,America/Los_Angeles\n"
    )


@pytest.fixture
def csv_text_with_comments():
    """CSV where some lines are comment lines starting with #."""
    return (
        "# This is a comment line\n"
        "server_id,date,start_time,stop_time,action,timezone\n"
        "# Another comment\n"
        f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,UTC\n"
    )


@pytest.fixture
def csv_with_past_session():
    """CSV that contains one past session (should be skipped) and one future session."""
    return (
        "server_id,date,start_time,stop_time,action,timezone\n"
        "win-server-1,2000-01-01,09:00,10:00,recording,UTC\n"
        f"win-server-1,{FUTURE_DATE},11:00,12:00,recording,UTC\n"
    )


# ---------------------------------------------------------------------------
# Fake server configuration
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_server_config():
    """A single fake server dict matching the structure of servers.yaml."""
    return {
        "win-server-1": {
            "name": "Test Windows Server",
            "platform": "windows",
            "host": "192.0.2.1",
            "ssh": {"user": "admin", "port": 22},
            "obs": {
                "path": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                "websocket_port": 4455,
            },
        },
        "mac-server-1": {
            "name": "Test Mac Server",
            "platform": "mac",
            "host": "192.0.2.2",
            "ssh": {"user": "admin", "port": 22},
            "obs": {
                "path": "/Applications/OBS.app/Contents/MacOS/obs",
                "websocket_port": 4455,
            },
        },
    }


# ---------------------------------------------------------------------------
# Sample servers YAML text
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_servers_yaml():
    """Raw YAML text representing a servers config file."""
    return """\
servers:
  win-server-1:
    name: "Windows Server 1"
    platform: windows
    host: "192.0.2.1"
    ssh:
      user: admin
      port: 22
    obs:
      path: 'C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe'
      websocket_port: 4455
  mac-server-1:
    name: "Mac Server 1"
    platform: mac
    host: "192.0.2.2"
    ssh:
      user: admin
      port: 22
    obs:
      path: "/Applications/OBS.app/Contents/MacOS/obs"
      websocket_port: 4455
"""


# ---------------------------------------------------------------------------
# Known server IDs set (mirrors keys in fake_server_config)
# ---------------------------------------------------------------------------

@pytest.fixture
def known_server_ids():
    return {"win-server-1", "mac-server-1"}


# ---------------------------------------------------------------------------
# Fake PEM key (not a real key — used only to satisfy paramiko mock calls)
# ---------------------------------------------------------------------------

FAKE_PEM = """\
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4PAtEsHAkiDqAPpRN7yLarKAhSm
wfX/TBpJDTMHFe1Hk4KQMH1mvRRBOWMBUFAKEFAKEFAKEFAKEFAKEFAKEFAKEF
-----END RSA PRIVATE KEY-----
"""

@pytest.fixture
def fake_pem():
    return FAKE_PEM


# ---------------------------------------------------------------------------
# Server config with close_exe set (for stop-path branching tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_server_config_with_close_exe():
    """A Windows server config with close_exe configured."""
    return {
        "win-server-1": {
            "name": "Test Windows Server",
            "platform": "windows",
            "host": "192.0.2.1",
            "ssh": {"user": "admin", "port": 22},
            "obs": {
                "path": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                "websocket_port": 4455,
                "close_exe": r"C:\Users\admin\Desktop\close.exe",
            },
        },
    }
