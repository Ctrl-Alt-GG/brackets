"""
The closed sets of values that the ORM mappings, the API models and the application share.

This module imports none of them, so each can depend on it.
"""

from enum import auto

from bracket.utils.i18n import gettext, gettext_noop
from bracket.utils.types import EnumAutoStr


class UserAccountType(EnumAutoStr):
    REGULAR = auto()


class TournamentRole(EnumAutoStr):
    """How someone runs a tournament: its owner, or an organizer the owner added."""

    OWNER = auto()
    COLLABORATOR = auto()


class TournamentStatus(EnumAutoStr):
    OPEN = auto()
    ARCHIVED = auto()


class StageType(EnumAutoStr):
    ROUND_ROBIN = auto()
    SINGLE_ELIMINATION = auto()
    SWISS = auto()

    @property
    def display_label(self) -> str:
        """The format's name in a sentence, such as "Round robin"."""
        return STAGE_TYPE_LABELS[self]

    @property
    def default_name(self) -> str:
        """The name a stage item of this format is stored with when it is created without one."""
        return self.display_label.title()

    @property
    def translated_label(self) -> str:
        """`display_label` in the language of the request."""
        return gettext(self.display_label)

    @property
    def supports_dynamic_number_of_rounds(self) -> bool:
        """Swiss rounds are drawn one at a time; the other formats get all of theirs up front."""
        return self is StageType.SWISS


STAGE_TYPE_LABELS = {
    StageType.ROUND_ROBIN: gettext_noop("Round robin"),
    StageType.SINGLE_ELIMINATION: gettext_noop("Single elimination"),
    StageType.SWISS: gettext_noop("Swiss"),
}
