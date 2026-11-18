"""
The closed sets of values that the ORM mappings, the API models and the application share.

This module imports none of them, so each can depend on it.
"""

from enum import auto

from bracket.utils.types import EnumAutoStr


class UserAccountType(EnumAutoStr):
    REGULAR = auto()


class UserXClubRelation(EnumAutoStr):
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
        return self.value.replace("_", " ").capitalize()

    @property
    def supports_dynamic_number_of_rounds(self) -> bool:
        """Swiss rounds are drawn one at a time; the other formats get all of theirs up front."""
        return self is StageType.SWISS
