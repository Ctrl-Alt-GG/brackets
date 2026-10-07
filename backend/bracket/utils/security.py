from collections.abc import Iterable

from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from zxcvbn import zxcvbn

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 72

# New passwords are hashed with Argon2. Older bcrypt hashes still verify, and are replaced by an
# Argon2 hash on the next login.
password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    """Whether the password is correct, and its new hash if the stored one is outdated."""
    return password_hash.verify_and_update(plain_password, hashed_password)


def normalize_email(email: str) -> str:
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc

    return validated_email.normalized.lower()


def validate_password_strength(password: str, disallowed_values: Iterable[str] = ()) -> str:
    if password.strip() != password:
        raise ValueError("Password must not start or end with whitespace")

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")

    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters long")

    # zxcvbn estimates how guessable the password is, also when it contains the user's details.
    strength = zxcvbn(password, user_inputs=[value for value in disallowed_values if value.strip()])
    if strength["score"] < 3:
        raise ValueError(
            " ".join(
                filter(
                    None, [strength["feedback"]["warning"], *strength["feedback"]["suggestions"]]
                )
            )
            or "Password is too easy to guess"
        )

    return password
