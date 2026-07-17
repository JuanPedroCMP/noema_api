from typing import Optional
import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'user'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='user_pk'),
        UniqueConstraint('primary_email', name='primary_email_uq'),
        UniqueConstraint('user_name', name='user_name_uq'),
        {'schema': 'app_auth'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(128), nullable=False)
    primary_email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    user_display_name: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))

    google_account: Mapped['GoogleAccount'] = relationship('GoogleAccount', uselist=False, back_populates='user')


class GoogleAccount(Base):
    __tablename__ = 'google_account'
    __table_args__ = (
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='google_account_pk'),
        UniqueConstraint('email_google', name='email_google_uq'),
        UniqueConstraint('google_user_id', name='google_user_id_uq'),
        UniqueConstraint('id_user', name='google_account_uq'),
        {'schema': 'app_auth'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    google_user_id: Mapped[Optional[str]] = mapped_column(Text)
    email_google: Mapped[Optional[str]] = mapped_column(String(254))
    access_token_enc: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token_enc: Mapped[Optional[str]] = mapped_column(Text)
    granted_scopes: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_refresh_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    user: Mapped['User'] = relationship('User', back_populates='google_account')
