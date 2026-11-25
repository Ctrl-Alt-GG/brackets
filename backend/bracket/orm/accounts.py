from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bracket.models.enums import UserAccountType
from bracket.orm.base import Base


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

    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
