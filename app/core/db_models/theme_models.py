from typing import Optional
import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Integer, JSON, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid, text
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

    user_color_theme: Mapped[list['UserColorTheme']] = relationship('UserColorTheme', back_populates='user')
    user_typography_theme: Mapped[list['UserTypographyTheme']] = relationship('UserTypographyTheme', back_populates='user')


class UserColorTheme(Base):
    __tablename__ = 'user_color_theme'
    __table_args__ = (
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='user_color_theme_pk'),
        UniqueConstraint('id_user', 'name', name='color_theme_name_uq'),
        {'schema': 'theme'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    seed_color: Mapped[Optional[int]] = mapped_column(Integer)
    override_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    user: Mapped['User'] = relationship('User', back_populates='user_color_theme')


class UserTypographyTheme(Base):
    __tablename__ = 'user_typography_theme'
    __table_args__ = (
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='user_typography_theme_pk'),
        UniqueConstraint('name', 'id_user', name='tipograph_theme_name_uq'),
        {'schema': 'theme'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    display_font: Mapped[Optional[str]] = mapped_column(String(255))
    body_font: Mapped[Optional[str]] = mapped_column(String(255))
    mono_font: Mapped[Optional[str]] = mapped_column(String(255))
    override_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    user: Mapped['User'] = relationship('User', back_populates='user_typography_theme')
