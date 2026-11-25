from collections.abc import Iterable

from anyio import CapacityLimiter, to_thread
from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from zxcvbn import zxcvbn

from bracket.utils.i18n import gettext

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 72

# New passwords are hashed with Argon2. Older bcrypt hashes still verify, and are replaced by an
# Argon2 hash on the next login.
password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


# Argon2 takes about a tenth of a second and 64 MiB of memory per hash, both on purpose. Requests
# hash in worker threads, so that the server keeps answering everyone else meanwhile. Only a few
# at a time, so that many logins arriving together can't exhaust the memory: the others wait.
PASSWORD_HASHING = CapacityLimiter(2)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    """Whether the password is correct, and its new hash if the stored one is outdated."""
    return password_hash.verify_and_update(plain_password, hashed_password)


async def hash_password_in_thread(password: str) -> str:
    """`hash_password` for request handlers."""
    return await to_thread.run_sync(hash_password, password, limiter=PASSWORD_HASHING)


async def verify_password_in_thread(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """`verify_password` for request handlers."""
    return await to_thread.run_sync(
        verify_password, plain_password, hashed_password, limiter=PASSWORD_HASHING
    )


def normalize_email(email: str) -> str:
    try:
        validated_email = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        # The library explains what is wrong in English only.
        raise ValueError(gettext("Enter a valid email address")) from exc

    return validated_email.normalized.lower()


def validate_password_strength(password: str, disallowed_values: Iterable[str] = ()) -> str:
    if password.strip() != password:
        raise ValueError(gettext("Password must not start or end with whitespace"))

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            gettext(
                "Password must be at least {minimum} characters long", minimum=PASSWORD_MIN_LENGTH
            )
        )

    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(
            gettext(
                "Password must be at most {maximum} characters long", maximum=PASSWORD_MAX_LENGTH
            )
        )

    # zxcvbn estimates how guessable the password is, also when it contains the user's details.
    strength = zxcvbn(password, user_inputs=[value for value in disallowed_values if value.strip()])
    if strength["score"] < 3:
        # zxcvbn's advice is in English, and the catalog translates it.
        feedback = [strength["feedback"]["warning"], *strength["feedback"]["suggestions"]]
        raise ValueError(
            " ".join(gettext(advice) for advice in feedback if advice)
            or gettext("Password is too easy to guess")
        )

    return password
