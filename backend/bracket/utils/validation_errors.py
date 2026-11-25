"""The field checks of a request, explained in the language of the request."""

from collections.abc import Mapping, Sequence
from typing import Any

from bracket.utils.i18n import gettext, ngettext


def _message(error_type: str, context: Mapping[str, Any]) -> str | None:
    """
    The message for Pydantic's checks that the API's requests can fail, in place of Pydantic's
    English one. The API's own checks are translated where they are written.
    """
    match error_type:
        # Pydantic's email check gives its reason in English. The API's own checks, which are
        # value errors too, have no reason: their message is translated already.
        case "value_error" if "reason" in context:
            return gettext("Enter a valid email address")
        case "missing":
            return gettext("This field is required")
        case "string_too_short":
            return ngettext(
                "Enter at least {count} character",
                "Enter at least {count} characters",
                context["min_length"],
            )
        case "string_too_long":
            return ngettext(
                "Enter at most {count} character",
                "Enter at most {count} characters",
                context["max_length"],
            )
        case "string_pattern_mismatch":
            return gettext("This doesn't have the expected format")
        case "string_type":
            return gettext("Enter text")
        case "int_parsing" | "int_type" | "int_from_float":
            return gettext("Enter a whole number")
        case "float_parsing" | "float_type" | "decimal_parsing" | "decimal_type":
            return gettext("Enter a number")
        case "decimal_max_places":
            return ngettext(
                "Use at most {count} decimal place",
                "Use at most {count} decimal places",
                context["decimal_places"],
            )
        case "greater_than":
            return gettext("Enter a number greater than {limit}", limit=context["gt"])
        case "greater_than_equal":
            return gettext("Enter {limit} or more", limit=context["ge"])
        case "less_than":
            return gettext("Enter a number less than {limit}", limit=context["lt"])
        case "less_than_equal":
            return gettext("Enter {limit} or less", limit=context["le"])
        case "bool_parsing" | "bool_type":
            return gettext("Enter true or false")
        case "enum" | "literal_error":
            return gettext("Choose one of these: {choices}", choices=context["expected"])
        case "datetime_parsing" | "datetime_from_date_parsing" | "datetime_type":
            return gettext("Enter a date and time")
        case "too_short":
            return ngettext(
                "Give at least {count} item", "Give at least {count} items", context["min_length"]
            )
        case "too_long":
            return ngettext(
                "Give at most {count} item", "Give at most {count} items", context["max_length"]
            )
        case "extra_forbidden":
            return gettext("This field isn't expected here")
        case "json_invalid":
            return gettext("This isn't valid JSON")
        case _:
            return None


def explain_validation_errors(errors: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Pydantic's errors, with the messages of the checks above in the language of the request."""
    explained: list[Mapping[str, Any]] = []
    for error in errors:
        try:
            message = _message(error["type"], error.get("ctx") or {})
        except KeyError:
            # A check that didn't say its limit keeps Pydantic's message, which does.
            message = None
        explained.append(error if message is None else {**error, "msg": message})
    return explained
