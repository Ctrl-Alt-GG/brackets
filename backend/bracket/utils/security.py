import re
from collections.abc import Iterable

import bcrypt
from email_validator import EmailNotValidError, validate_email

COMMON_PASSWORDS = {
    "12345678",
    "123456789",
    "1234567890",
    "adminadmin",
    "letmein123",
    "password",
    "password12",
    "password123",
    "qwerty123",
    "welcome123",
}

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def normalize_email(email: str) -> str:
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc

    return validated_email.normalized.lower()


def validate_password_strength(password: str, disallowed_values: Iterable[str] = ()) -> str:
    normalized_password = password.strip()
    if normalized_password != password:
        raise ValueError("Password must not start or end with whitespace")

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")

    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters long")

    if password.casefold() in COMMON_PASSWORDS:
        raise ValueError("Password is too common")

    lowered_password = password.casefold()
    for disallowed_value in disallowed_values:
        stripped_value = disallowed_value.strip()
        if stripped_value and stripped_value.casefold() in lowered_password:
            raise ValueError("Password must not contain your personal details")

    category_count = sum(
        (
            bool(re.search(r"[a-z]", password)),
            bool(re.search(r"[A-Z]", password)),
            bool(re.search(r"\d", password)),
            bool(re.search(r"[^A-Za-z0-9]", password)),
        )
    )
    if category_count < 3:
        raise ValueError(
            "Password must include at least three of the following: lowercase letters, "
            "uppercase letters, numbers, and symbols"
        )

    return password
