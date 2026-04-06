"""
tests/unit/test_schedule_loader.py

Unit tests for src/schedule_loader.py :: load_schedule()
"""

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from schedule_loader import load_schedule, ScheduleEntry

# Far-future date used throughout so rows are never skipped as "past"
FUTURE_DATE = "2099-01-15"
FUTURE_DATE_2 = "2099-01-16"


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestLoadScheduleValidInput:

    def test_valid_csv_returns_schedule_entry_list(self, valid_csv_text):
        entries = load_schedule(valid_csv_text)

        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, ScheduleEntry)

    def test_valid_csv_has_correct_server_id(self, valid_csv_text):
        entries = load_schedule(valid_csv_text)

        assert entries[0].server_id == "win-server-1"

    def test_valid_csv_has_correct_action(self, valid_csv_text):
        entries = load_schedule(valid_csv_text)

        assert entries[0].action == "recording"

    def test_valid_csv_start_dt_is_timezone_aware(self, valid_csv_text):
        entries = load_schedule(valid_csv_text)

        assert entries[0].start_dt.tzinfo is not None

    def test_valid_csv_stop_dt_is_timezone_aware(self, valid_csv_text):
        entries = load_schedule(valid_csv_text)

        assert entries[0].stop_dt.tzinfo is not None

    def test_valid_csv_stop_dt_after_start_dt(self, valid_csv_text):
        entries = load_schedule(valid_csv_text)

        assert entries[0].stop_dt > entries[0].start_dt

    def test_multiple_rows_returns_all_entries(self, multi_row_csv_text):
        entries = load_schedule(multi_row_csv_text)

        assert len(entries) == 2

    def test_action_is_lowercased(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,RECORDING,UTC\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].action == "recording"

    def test_streaming_action_accepted(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,streaming,UTC\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].action == "streaming"

    def test_columns_with_leading_trailing_spaces_are_stripped(self):
        csv_text = (
            " server_id , date , start_time , stop_time , action , timezone \n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,UTC\n"
        )
        entries = load_schedule(csv_text)

        assert len(entries) == 1

    def test_row_values_with_leading_trailing_spaces_are_stripped(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f" win-server-1 ,{FUTURE_DATE}, 09:00 , 10:00 , recording , UTC \n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].server_id == "win-server-1"


# ---------------------------------------------------------------------------
# Comment line tests
# ---------------------------------------------------------------------------

class TestLoadScheduleCommentLines:

    def test_comment_lines_are_ignored(self, csv_text_with_comments):
        entries = load_schedule(csv_text_with_comments)

        assert len(entries) == 1

    def test_comment_only_csv_raises_value_error(self):
        csv_text = "# just a comment\n# another comment\n"

        with pytest.raises(ValueError, match="empty or has no header row"):
            load_schedule(csv_text)


# ---------------------------------------------------------------------------
# Past-session skip tests
# ---------------------------------------------------------------------------

class TestLoadSchedulePastSessions:

    def test_past_sessions_are_silently_skipped(self, csv_with_past_session):
        entries = load_schedule(csv_with_past_session)

        assert len(entries) == 1
        # The surviving entry must be the future one
        assert entries[0].server_id == "win-server-1"

    def test_all_past_sessions_returns_empty_list(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            "win-server-1,2000-01-01,09:00,10:00,recording,UTC\n"
            "win-server-1,2000-01-02,11:00,12:00,recording,UTC\n"
        )
        entries = load_schedule(csv_text)

        assert entries == []


# ---------------------------------------------------------------------------
# Missing-column validation
# ---------------------------------------------------------------------------

class TestLoadScheduleMissingColumns:

    def test_missing_server_id_column_raises_value_error(self):
        csv_text = (
            "date,start_time,stop_time,action,timezone\n"
            f"{FUTURE_DATE},09:00,10:00,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="missing required columns"):
            load_schedule(csv_text)

    def test_missing_date_column_raises_value_error(self):
        csv_text = (
            "server_id,start_time,stop_time,action,timezone\n"
            "win-server-1,09:00,10:00,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="missing required columns"):
            load_schedule(csv_text)

    def test_missing_action_column_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,UTC\n"
        )
        with pytest.raises(ValueError, match="missing required columns"):
            load_schedule(csv_text)

    def test_empty_csv_raises_value_error(self):
        with pytest.raises(ValueError, match="empty or has no header row"):
            load_schedule("")


# ---------------------------------------------------------------------------
# Invalid timezone
# ---------------------------------------------------------------------------

class TestLoadScheduleInvalidTimezone:

    def test_invalid_timezone_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,Not/A/Timezone\n"
        )
        with pytest.raises(ValueError, match="unknown timezone"):
            load_schedule(csv_text)

    def test_blank_timezone_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,\n"
        )
        with pytest.raises(ValueError, match="unknown timezone"):
            load_schedule(csv_text)


# ---------------------------------------------------------------------------
# Unknown server_id
# ---------------------------------------------------------------------------

class TestLoadScheduleUnknownServerID:

    def test_unknown_server_id_raises_value_error_when_known_ids_provided(
        self, known_server_ids
    ):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"nonexistent-server,{FUTURE_DATE},09:00,10:00,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="not found in servers.yaml"):
            load_schedule(csv_text, known_server_ids=known_server_ids)

    def test_unknown_server_id_does_not_raise_when_known_ids_not_provided(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"any-server-id,{FUTURE_DATE},09:00,10:00,recording,UTC\n"
        )
        entries = load_schedule(csv_text)

        assert len(entries) == 1

    def test_known_server_id_is_accepted(self, known_server_ids):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,UTC\n"
        )
        entries = load_schedule(csv_text, known_server_ids=known_server_ids)

        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Stop time before start time
# ---------------------------------------------------------------------------

class TestLoadScheduleStopBeforeStart:

    def test_stop_time_equal_to_start_time_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,09:00,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="stop_time.*must be after start_time"):
            load_schedule(csv_text)

    def test_stop_time_before_start_time_treated_as_overnight(self):
        """When stop_time < start_time, the session crosses midnight."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},22:00,06:00,recording,UTC\n"
        )
        entries = load_schedule(csv_text)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.stop_dt > entry.start_dt
        # stop should be on the next day
        assert entry.stop_dt.day != entry.start_dt.day


# ---------------------------------------------------------------------------
# Invalid date/time format
# ---------------------------------------------------------------------------

class TestLoadScheduleInvalidDateTimeFormat:

    def test_invalid_date_format_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            "win-server-1,15/01/2099,09:00,10:00,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="cannot parse date/time"):
            load_schedule(csv_text)

    def test_invalid_time_format_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},9am,10am,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="cannot parse date/time"):
            load_schedule(csv_text)

    def test_empty_date_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            "win-server-1,,09:00,10:00,recording,UTC\n"
        )
        with pytest.raises(ValueError, match="cannot parse date/time"):
            load_schedule(csv_text)


# ---------------------------------------------------------------------------
# Invalid action
# ---------------------------------------------------------------------------

class TestLoadScheduleInvalidAction:

    def test_invalid_action_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,broadcasting,UTC\n"
        )
        with pytest.raises(ValueError, match="invalid action"):
            load_schedule(csv_text)

    def test_empty_action_raises_value_error(self):
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,,UTC\n"
        )
        with pytest.raises(ValueError, match="invalid action"):
            load_schedule(csv_text)


# ---------------------------------------------------------------------------
# UTC conversion accuracy
# ---------------------------------------------------------------------------

class TestLoadScheduleUtcConversion:

    def test_new_york_time_converted_to_correct_utc(self):
        """America/New_York 09:00 on a non-DST date should become 14:00 UTC."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            # January 15 is not DST, so EST = UTC-5
            f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,America/New_York\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].start_dt.hour == 14  # 09:00 EST = 14:00 UTC
        assert entries[0].stop_dt.hour == 15   # 10:00 EST = 15:00 UTC


# ---------------------------------------------------------------------------
# Optional title column tests
# ---------------------------------------------------------------------------

class TestLoadScheduleTitleColumn:

    def test_csv_without_title_column_returns_none_title(self):
        """Backward compatibility: CSV without title column sets title to None."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,recording,UTC\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].title is None

    def test_csv_with_title_column_parses_title(self):
        """Title column present with a value is parsed correctly."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone,title\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,streaming,UTC,Palm Sunday - Divine Liturgy\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].title == "Palm Sunday - Divine Liturgy"

    def test_csv_with_blank_title_returns_none(self):
        """Blank title column value is treated as None."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone,title\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,streaming,UTC,\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].title is None

    def test_csv_with_whitespace_only_title_returns_none(self):
        """Whitespace-only title is treated as None."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone,title\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,streaming,UTC,   \n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].title is None

    def test_csv_with_title_preserves_original_casing(self):
        """Title should preserve original casing, not be lowered or altered."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone,title\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,streaming,UTC,Arabic Bible Study\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].title == "Arabic Bible Study"

    def test_csv_mixed_rows_with_and_without_title(self):
        """When title column exists, some rows can have title and others can be blank."""
        csv_text = (
            "server_id,date,start_time,stop_time,action,timezone,title\n"
            f"win-server-1,{FUTURE_DATE},09:00,10:00,streaming,UTC,Palm Sunday\n"
            f"win-server-1,{FUTURE_DATE},11:00,12:00,streaming,UTC,\n"
        )
        entries = load_schedule(csv_text)

        assert entries[0].title == "Palm Sunday"
        assert entries[1].title is None
