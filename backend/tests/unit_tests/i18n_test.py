"""The API's messages in Hungarian, for requests that ask for it with `Accept-Language`."""

import ast
import string
from collections.abc import Iterable, Iterator
from pathlib import Path

import anyio
import polib
import pytest
import zxcvbn.feedback
from starlette.concurrency import run_in_threadpool
from starlette.types import Message, Receive, Scope, Send

from bracket.models.enums import StageType
from bracket.utils.i18n import (
    LanguageMiddleware,
    catalog_path,
    gettext,
    negotiate_language,
    round_label,
    stage_label,
    use_language,
)
from bracket.utils.security import validate_password_strength
from bracket.utils.validation_errors import explain_validation_errors

CATALOG = polib.pofile(str(catalog_path("hu")))

# Placeholders a translation may use although its message doesn't: the call passes them too.
EXTRA_PLACEHOLDERS = {"Round {padded}": {"number"}}


def marked_messages(paths: Iterable[Path], functions: set[str]) -> set[tuple[str, ...]]:
    """
    The messages that calls of `functions` in `paths` translate: the message, or both forms of
    one that `ngettext` translates.
    """
    messages: set[tuple[str, ...]] = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in functions
            ):
                continue
            forms = [
                form.value
                for form in node.args[: 2 if node.func.id == "ngettext" else 1]
                if isinstance(form, ast.Constant) and isinstance(form.value, str)
            ]
            if forms:
                messages.add(tuple(forms))
    return messages


CODE_MESSAGES = marked_messages(
    Path("bracket").rglob("*.py"), {"gettext", "ngettext", "gettext_noop"}
)
# zxcvbn's password advice is English, and the catalog translates it as well.
ZXCVBN_MESSAGES = marked_messages([Path(zxcvbn.feedback.__file__)], {"_"})


def catalog_key(entry: polib.POEntry) -> tuple[str, ...]:
    return (entry.msgid, entry.msgid_plural) if entry.msgid_plural else (entry.msgid,)


def placeholders(text: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


@pytest.fixture
def hungarian() -> Iterator[None]:
    use_language("hu")
    try:
        yield
    finally:
        use_language("en")


def test_every_message_has_a_hungarian_translation() -> None:
    translated = {catalog_key(entry) for entry in CATALOG.translated_entries()}

    assert CODE_MESSAGES, "No messages found: is the test run from backend/?"
    assert sorted((CODE_MESSAGES | ZXCVBN_MESSAGES) - translated) == []


def test_the_catalog_has_no_messages_that_nothing_uses() -> None:
    unused = {catalog_key(entry) for entry in CATALOG} - CODE_MESSAGES - ZXCVBN_MESSAGES

    assert sorted(unused) == []


def test_translations_keep_the_placeholders_of_their_message() -> None:
    for entry in CATALOG:
        allowed = placeholders(entry.msgid) | EXTRA_PLACEHOLDERS.get(entry.msgid, set())
        translations = [entry.msgstr]
        if entry.msgid_plural:
            allowed |= placeholders(entry.msgid_plural)
            translations = list(entry.msgstr_plural.values())
        for translation in translations:
            assert placeholders(translation) <= allowed, entry.msgid


@pytest.mark.parametrize(
    ("accept_language", "language"),
    [
        (None, "en"),
        ("", "en"),
        ("hu", "hu"),
        ("HU", "hu"),
        ("hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7", "hu"),
        ("en-GB,en;q=0.9,hu;q=0.8", "en"),
        # A language the API doesn't speak is skipped for the next one.
        ("de-DE,de;q=0.9,hu;q=0.5", "hu"),
        ("de-DE", "en"),
        ("hu;q=0", "en"),
        ("*", "en"),
        ("hu;q=nonsense", "en"),
    ],
)
def test_the_language_is_the_one_the_client_prefers_most(
    accept_language: str | None, language: str
) -> None:
    assert negotiate_language(accept_language) == language


@pytest.mark.usefixtures("hungarian")
def test_names_the_api_gave_are_shown_in_the_language_of_the_request() -> None:
    assert round_label("Round 03") == "3. forduló"
    assert round_label("Döntő") == "Döntő"
    assert stage_label("Stage") == "Szakasz"
    assert stage_label("Csoportkör") == "Csoportkör"
    assert StageType.SWISS.translated_label == "Svájci rendszer"


def test_english_keeps_the_names_the_api_gave() -> None:
    assert round_label("Round 03") == "Round 03"
    assert stage_label("Stage") == "Stage"
    assert StageType.ROUND_ROBIN.translated_label == "Round robin"


@pytest.mark.usefixtures("hungarian")
def test_field_checks_are_explained_in_the_language_of_the_request() -> None:
    own_check = {
        "type": "value_error",
        "msg": "Value error, Adj meg legalább egy csapatot",
        "ctx": {"error": ValueError("Adj meg legalább egy csapatot")},
    }
    unknown = {"type": "url_parsing", "msg": "Input should be a valid URL"}

    explained = explain_validation_errors(
        [
            {"type": "string_too_short", "msg": "String should have…", "ctx": {"min_length": 1}},
            {"type": "missing", "msg": "Field required"},
            {"type": "value_error", "msg": "value is not…", "ctx": {"reason": "No @-sign."}},
            own_check,
            unknown,
            # A check without the limit it names keeps Pydantic's message.
            {"type": "greater_than_equal", "msg": "Input should be greater than or equal to 1"},
        ]
    )

    assert [error["msg"] for error in explained] == [
        "Legalább 1 karaktert adj meg",
        "Ezt a mezőt ki kell tölteni",
        "Érvényes e-mail-címet adj meg",
        "Value error, Adj meg legalább egy csapatot",
        "Input should be a valid URL",
        "Input should be greater than or equal to 1",
    ]


@pytest.mark.usefixtures("hungarian")
def test_password_advice_is_in_the_language_of_the_request() -> None:
    with pytest.raises(ValueError) as refused:
        validate_password_strength("aaaaaaaaaaaa")

    assert str(refused.value) == (
        "Az olyan ismétléseket, mint az „aaa”, könnyű kitalálni. "
        "Adj hozzá még egy-két szót. A ritka szavak jobbak. "
        "Kerüld az ismétlődő szavakat és karaktereket."
    )


async def test_messages_written_in_worker_threads_follow_the_request() -> None:
    # Password checks and logos are handled in worker threads.
    use_language("hu")
    try:
        assert await run_in_threadpool(gettext, "Logo not found") == "A logó nem található"
        assert await anyio.to_thread.run_sync(gettext, "Logo not found") == "A logó nem található"
    finally:
        use_language("en")


async def answer_with_message(scope: Scope, receive: Receive, send: Send) -> None:
    """An app whose answer is a message of the catalog."""
    await send({"type": "http.response.start", "status": 404, "headers": []})
    await send({"type": "http.response.body", "body": gettext("Logo not found").encode()})


async def request(headers: list[tuple[bytes, bytes]]) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    try:
        await LanguageMiddleware(answer_with_message)(scope, receive, send)
    finally:
        use_language("en")
    return sent


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ([(b"accept-language", b"hu-HU,hu;q=0.9")], "A logó nem található"),
        ([(b"accept-language", b"en")], "Logo not found"),
        ([], "Logo not found"),
    ],
)
async def test_answers_are_in_the_language_of_the_request(
    headers: list[tuple[bytes, bytes]], body: str
) -> None:
    start, content = await request(headers)

    assert content["body"].decode() == body
    # Caches keep the answers of each language apart.
    assert (b"vary", b"Accept-Language") in start["headers"]
