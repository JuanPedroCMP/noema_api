from typing import Optional
import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Integer, JSON, PrimaryKeyConstraint, SmallInteger, String, Text, UniqueConstraint, Uuid, text
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

    device: Mapped[list['Device']] = relationship('Device', back_populates='user')
    user_color_theme: Mapped[list['UserColorTheme']] = relationship('UserColorTheme', back_populates='user')
    user_typography_theme: Mapped[list['UserTypographyTheme']] = relationship('UserTypographyTheme', back_populates='user')
    response_language_preference_order: Mapped[list['ResponseLanguagePreferenceOrder']] = relationship('ResponseLanguagePreferenceOrder', back_populates='user')
    user_global_config: Mapped['UserGlobalConfig'] = relationship('UserGlobalConfig', uselist=False, back_populates='user')
    user_local_config: Mapped[list['UserLocalConfig']] = relationship('UserLocalConfig', back_populates='user')


class Language(Base):
    __tablename__ = 'language'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='language_pk'),
        UniqueConstraint('name', name='name_uq'),
        {'schema': 'user_config'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(55), nullable=False)
    percentage_translated: Mapped[Optional[int]] = mapped_column(SmallInteger)
    verified_translation: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    automatic_translation: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    response_language_preference_order: Mapped[list['ResponseLanguagePreferenceOrder']] = relationship('ResponseLanguagePreferenceOrder', back_populates='language')
    user_global_config: Mapped[list['UserGlobalConfig']] = relationship('UserGlobalConfig', back_populates='language')
    user_local_config: Mapped[list['UserLocalConfig']] = relationship('UserLocalConfig', back_populates='language')


class Device(Base):
    __tablename__ = 'device'
    __table_args__ = (
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='device_pk'),
        {'schema': 'device'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(64))
    platform: Mapped[Optional[str]] = mapped_column(String(32))
    last_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    user: Mapped['User'] = relationship('User', back_populates='device')
    user_local_config: Mapped[list['UserLocalConfig']] = relationship('UserLocalConfig', back_populates='device')


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
    user_global_config: Mapped[list['UserGlobalConfig']] = relationship('UserGlobalConfig', back_populates='user_color_theme')
    user_local_config: Mapped[list['UserLocalConfig']] = relationship('UserLocalConfig', back_populates='user_color_theme')


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
    user_global_config: Mapped[list['UserGlobalConfig']] = relationship('UserGlobalConfig', back_populates='user_typography_theme')
    user_local_config: Mapped[list['UserLocalConfig']] = relationship('UserLocalConfig', back_populates='user_typography_theme')


class ResponseLanguagePreferenceOrder(Base):
    __tablename__ = 'response_language_preference_order'
    __table_args__ = (
        ForeignKeyConstraint(['id_language'], ['user_config.language.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='language_fk'),
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='response_language_preference_order_pk'),
        UniqueConstraint('id_language', 'id_user', name='user_language_uq'),
        {'schema': 'user_config'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_language: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    preference_order: Mapped[Optional[int]] = mapped_column(SmallInteger)

    language: Mapped['Language'] = relationship('Language', back_populates='response_language_preference_order')
    user: Mapped['User'] = relationship('User', back_populates='response_language_preference_order')


class UserGlobalConfig(Base):
    __tablename__ = 'user_global_config'
    __table_args__ = (
        ForeignKeyConstraint(['id_language'], ['user_config.language.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='language_fk'),
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        ForeignKeyConstraint(['id_user_color_theme'], ['theme.user_color_theme.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='user_color_theme_fk'),
        ForeignKeyConstraint(['id_user_typography_theme'], ['theme.user_typography_theme.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='user_typography_theme_fk'),
        PrimaryKeyConstraint('id', name='user_global_config_pk'),
        UniqueConstraint('id_user', name='user_global_config_uq'),
        {'schema': 'user_config'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_language: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False)
    id_user_color_theme: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    id_user_typography_theme: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    language: Mapped['Language'] = relationship('Language', back_populates='user_global_config')
    user: Mapped['User'] = relationship('User', back_populates='user_global_config')
    user_color_theme: Mapped[Optional['UserColorTheme']] = relationship('UserColorTheme', back_populates='user_global_config')
    user_typography_theme: Mapped[Optional['UserTypographyTheme']] = relationship('UserTypographyTheme', back_populates='user_global_config')


class UserLocalConfig(Base):
    __tablename__ = 'user_local_config'
    __table_args__ = (
        ForeignKeyConstraint(['id_device'], ['device.device.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='device_fk'),
        ForeignKeyConstraint(['id_language'], ['user_config.language.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='language_fk'),
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        ForeignKeyConstraint(['id_user_color_theme'], ['theme.user_color_theme.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='user_color_theme_fk'),
        ForeignKeyConstraint(['id_user_typography_theme'], ['theme.user_typography_theme.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='user_typography_theme_fk'),
        PrimaryKeyConstraint('id', name='user_local_config_pk'),
        UniqueConstraint('id_user', 'id_device', name='id_user_id_device_uq'),
        {'schema': 'user_config'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_language: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_device: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_user_typography_theme: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    id_user_color_theme: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    device: Mapped['Device'] = relationship('Device', back_populates='user_local_config')
    language: Mapped['Language'] = relationship('Language', back_populates='user_local_config')
    user: Mapped['User'] = relationship('User', back_populates='user_local_config')
    user_color_theme: Mapped[Optional['UserColorTheme']] = relationship('UserColorTheme', back_populates='user_local_config')
    user_typography_theme: Mapped[Optional['UserTypographyTheme']] = relationship('UserTypographyTheme', back_populates='user_local_config')
