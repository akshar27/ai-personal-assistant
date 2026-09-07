import pytest

from graph.nodes import extract_requested_hour, normalize_local_iso


@pytest.mark.parametrize(
    "message, expected",
    [
        ("schedule a meeting at 3pm", 15),
        ("call at 9 am tomorrow", 9),
        ("meet at 12pm", 12),
        ("meet at 12am", 0),
        ("meeting at 3:30 pm", 15),
        ("sometime tomorrow afternoon", None),
        ("at 3", None),  # no am/pm → ambiguous, don't guess
    ],
)
def test_extract_requested_hour(message, expected):
    assert extract_requested_hour(message) == expected


def test_normalize_local_iso_strips_trailing_z_and_converts_to_local():
    # 22:00 UTC → 15:00 America/Los_Angeles (PDT, -7)
    out = normalize_local_iso("2026-07-01T22:00:00Z")
    assert out == "2026-07-01T15:00:00"
    assert "Z" not in out and "+" not in out


def test_normalize_local_iso_passes_naive_through_unchanged():
    assert normalize_local_iso("2026-07-01T15:00:00") == "2026-07-01T15:00:00"


def test_normalize_local_iso_handles_empty():
    assert normalize_local_iso("") == ""
    assert normalize_local_iso(None) == ""
