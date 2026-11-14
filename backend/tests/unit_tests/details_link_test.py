import pytest

from bracket.utils.pydantic import validate_dashboard_endpoint


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Summer-Cup_2026", "summer-cup_2026"), ("  cup  ", "cup"), ("   ", None), (None, None)],
)
def test_details_links_are_stored_in_lowercase(value: str | None, expected: str | None) -> None:
    assert validate_dashboard_endpoint(value) == expected


@pytest.mark.parametrize("value", ["2026", "summer cup", "nyári-kupa"])
def test_details_links_need_a_letter_and_only_url_safe_characters(value: str) -> None:
    with pytest.raises(ValueError):
        validate_dashboard_endpoint(value)
