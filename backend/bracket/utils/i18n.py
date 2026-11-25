"""
The API's messages in the language a request asks for with `Accept-Language`: Hungarian or
English. The frontend asks for the language of the page. Clients that don't ask get English.

The Hungarian texts are in `bracket/locale/hu/LC_MESSAGES/messages.po`, under the English message
they translate. Messages name their variable parts as `{name}`, filled in after translation, so
that a translation can put them where its language needs them.
"""

import re
from contextvars import ContextVar
from gettext import GNUTranslations, NullTranslations
from io import BytesIO
from pathlib import Path

import polib
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOCALE_DIR = Path(__file__).parent.parent / "locale"
DEFAULT_LANGUAGE = "en"


def catalog_path(language: str) -> Path:
    return LOCALE_DIR / language / "LC_MESSAGES" / "messages.po"


def _load(language: str) -> GNUTranslations:
    # The catalog is compiled when the API starts, so the repository holds only the text file.
    compiled = polib.pofile(str(catalog_path(language))).to_binary()
    return GNUTranslations(BytesIO(compiled))


TRANSLATIONS: dict[str, NullTranslations] = {
    # The messages are written in English.
    DEFAULT_LANGUAGE: NullTranslations(),
    "hu": _load("hu"),
}

_translations: ContextVar[NullTranslations] = ContextVar(
    "translations", default=TRANSLATIONS[DEFAULT_LANGUAGE]
)


def negotiate_language(accept_language: str | None) -> str:
    """The language of the API that the client prefers most, by `Accept-Language`."""
    preferences: list[tuple[float, int, str]] = []
    for index, entry in enumerate((accept_language or "").split(",")):
        tag, *parameters = (part.strip() for part in entry.split(";"))
        quality = 1.0
        for parameter in parameters:
            name, _, value = parameter.partition("=")
            if name.strip() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0
        # "hu-HU" asks for Hungarian.
        language = tag.split("-")[0].lower()
        if quality > 0 and language in TRANSLATIONS:
            preferences.append((-quality, index, language))
    return min(preferences)[2] if preferences else DEFAULT_LANGUAGE


def use_language(language: str) -> None:
    """Translates the messages of the current request, or test, into `language`."""
    _translations.set(TRANSLATIONS[language])


class LanguageMiddleware:
    """Gives each request its messages in the language it asks for."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Every request runs in a context of its own, so the language stays with this request.
        # It is not reset afterwards, so that the handler of an unexpected error, which runs
        # outside the middlewares, answers in it too.
        use_language(negotiate_language(Headers(scope=scope).get("accept-language")))

        async def send_with_vary(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).add_vary_header("Accept-Language")
            await send(message)

        await self.app(scope, receive, send_with_vary)


def gettext(message: str, **values: object) -> str:
    """`message` in the request's language, with its `{name}` parts filled from `values`."""
    translated = _translations.get().gettext(message)
    return translated.format(**values) if values else translated


def ngettext(singular: str, plural: str, count: int, **values: object) -> str:
    """Like `gettext`, in the form for `count`, which fills in `{count}`."""
    return _translations.get().ngettext(singular, plural, count).format(count=count, **values)


def gettext_noop(message: str) -> str:
    """Marks a message that is translated later, where it is used, with `gettext(message)`."""
    return message


# The API names the rounds it creates "Round 01" and so on, and a new stage "Stage". Those names
# are stored, and shown in the language of the request.
_GENERATED_ROUND_NAME = re.compile(r"^Round (\d+)$")
DEFAULT_STAGE_NAME = gettext_noop("Stage")


def round_label(name: str) -> str:
    if (generated := _GENERATED_ROUND_NAME.match(name)) is None:
        return name
    return gettext("Round {padded}", number=int(generated[1]), padded=generated[1])


def stage_label(name: str) -> str:
    return gettext(DEFAULT_STAGE_NAME) if name == DEFAULT_STAGE_NAME else name
