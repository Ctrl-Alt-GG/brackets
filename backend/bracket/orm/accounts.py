from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bracket.models.db.account import UserAccountType
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.orm.base import Base

if TYPE_CHECKING:
    from bracket.orm.tournaments import Tournament


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    memberships: Mapped[list[UserXClub]] = relationship(
        back_populates="club", lazy="raise", passive_deletes=True
    )
    tournaments: Mapped[list[Tournament]] = relationship(lazy="raise", passive_deletes="all")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    account_type: Mapped[UserAccountType] = mapped_column(
        Enum(UserAccountType, name="account_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    memberships: Mapped[list[UserXClub]] = relationship(
        back_populates="user", lazy="raise", passive_deletes=True
    )

    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class UserXClub(Base):
    __tablename__ = "users_x_clubs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[UserXClubRelation] = mapped_column(
        Enum(
            UserXClubRelation,
            name="user_x_club_relation",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=UserXClubRelation.OWNER,
    )
    club: Mapped[Club] = relationship(back_populates="memberships", lazy="raise")
    user: Mapped[User] = relationship(back_populates="memberships", lazy="raise")

    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="users_x_clubs_club_id_user_id_key"),
        Index(
            "uq_users_x_clubs_owner",
            "club_id",
            unique=True,
            postgresql_where=relation == UserXClubRelation.OWNER,
        ),
        Index("ix_users_x_clubs_user_id", "user_id"),
    )
