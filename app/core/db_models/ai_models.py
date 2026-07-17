from typing import Optional
import datetime
import decimal
import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKeyConstraint, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class AgentModelQuality(str, enum.Enum):
    UNUSABLE = 'unusable'
    POOR = 'poor'
    FAIR = 'fair'
    GOOD = 'good'
    VERY_GOOD = 'very_good'
    EXCELLENT = 'excellent'


class TaskType(str, enum.Enum):
    MANIPULATE_GRAPH = 'manipulate_graph'
    MANIPULATE_NODE = 'manipulate_node'
    CREATE_STUDY_SESSION = 'create_study_session'
    EVALUATE_ESSAY_QUESTION = 'evaluate_essay_question'
    CREATE_ESSAY_QUESTION = 'create_essay_question'
    CREATE_MULTIPLE_CHOICE_QUESTION = 'create_multiple_choice_question'
    EVALUATE_MULTIPLE_CHOICE_QUESTION = 'evaluate_multiple_choice_question'
    CREATE_FEYNMAN = 'create_feynman'
    EVALUATE_FEYNMAN_ = 'evaluate_feynman '
    RECOMMEND_STUDY_RESOURCE = 'recommend_study_resource'
    STUDY_MANAGER = 'study_manager'
    STUDY_ASSISTENT = 'study_assistent'


class Agent(Base):
    __tablename__ = 'agent'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='agent_pk'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    task: Mapped[TaskType] = mapped_column(Enum(TaskType, values_callable=lambda cls: [member.value for member in cls], name='task_type', schema='ai'), nullable=False)
    base_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2), comment='Deve estar entre 0 e 2')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    agent_model: Mapped[list['AgentModel']] = relationship('AgentModel', back_populates='agent')


class AiProvider(Base):
    __tablename__ = 'ai_provider'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='ai_provider_pk'),
        UniqueConstraint('slug', name='ai_provider_slug_uq'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    ai_model: Mapped[list['AiModel']] = relationship('AiModel', back_populates='ai_provider')
    user_api_key: Mapped[list['UserApiKey']] = relationship('UserApiKey', back_populates='ai_provider')


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

    user_api_key: Mapped[list['UserApiKey']] = relationship('UserApiKey', back_populates='user')
    ai_usage_log: Mapped[list['AiUsageLog']] = relationship('AiUsageLog', back_populates='user')


class AiModel(Base):
    __tablename__ = 'ai_model'
    __table_args__ = (
        ForeignKeyConstraint(['id_ai_provider'], ['ai.ai_provider.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='ai_provider_fk'),
        PrimaryKeyConstraint('id', name='ai_model_pk'),
        UniqueConstraint('slug', name='ai_model_slug_uq'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_ai_provider: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    context_window: Mapped[Optional[int]] = mapped_column(Integer)
    input_token_limit: Mapped[Optional[int]] = mapped_column(Integer)
    output_token_limit: Mapped[Optional[int]] = mapped_column(Integer)
    supports_vision: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    ai_provider: Mapped['AiProvider'] = relationship('AiProvider', back_populates='ai_model')
    agent_model: Mapped[list['AgentModel']] = relationship('AgentModel', back_populates='ai_model')
    user_api_key_can_use_ia_model: Mapped[list['UserApiKeyCanUseIaModel']] = relationship('UserApiKeyCanUseIaModel', back_populates='ai_model')


class UserApiKey(Base):
    __tablename__ = 'user_api_key'
    __table_args__ = (
        ForeignKeyConstraint(['id_ai_provider'], ['ai.ai_provider.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='ai_provider_fk'),
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='user_api_key_pk'),
        UniqueConstraint('encrypted_key', 'id_user', name='key_user_uq'),
        UniqueConstraint('name', 'id_user', name='key_name_uq'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_ai_provider: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    ai_provider: Mapped['AiProvider'] = relationship('AiProvider', back_populates='user_api_key')
    user: Mapped['User'] = relationship('User', back_populates='user_api_key')
    user_api_key_can_use_ia_model: Mapped[list['UserApiKeyCanUseIaModel']] = relationship('UserApiKeyCanUseIaModel', back_populates='user_api_key')


class AgentModel(Base):
    __tablename__ = 'agent_model'
    __table_args__ = (
        ForeignKeyConstraint(['id_agent'], ['ai.agent.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='agent_fk'),
        ForeignKeyConstraint(['id_ai_model'], ['ai.ai_model.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='ai_model_fk'),
        PrimaryKeyConstraint('id', name='task_model_preference_pk'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_agent: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_ai_model: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    custom_system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    custom_temperature: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    quality_expected: Mapped[Optional[AgentModelQuality]] = mapped_column(Enum(AgentModelQuality, values_callable=lambda cls: [member.value for member in cls], name='agent_model_quality', schema='ai'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    agent: Mapped['Agent'] = relationship('Agent', back_populates='agent_model')
    ai_model: Mapped['AiModel'] = relationship('AiModel', back_populates='agent_model')
    ai_usage_log: Mapped[list['AiUsageLog']] = relationship('AiUsageLog', back_populates='agent_model')


class UserApiKeyCanUseIaModel(Base):
    __tablename__ = 'user_api_key_can_use_ia_model'
    __table_args__ = (
        ForeignKeyConstraint(['id_ai_model'], ['ai.ai_model.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='ai_model_fk'),
        ForeignKeyConstraint(['id_user_api_key'], ['ai.user_api_key.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_api_key_fk'),
        PrimaryKeyConstraint('id', name='user_api_key_can_use_ia_model_pk'),
        UniqueConstraint('id_user_api_key', 'id_ai_model', name='api_key_ia_model_uq'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user_api_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_ai_model: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    ai_model: Mapped['AiModel'] = relationship('AiModel', back_populates='user_api_key_can_use_ia_model')
    user_api_key: Mapped['UserApiKey'] = relationship('UserApiKey', back_populates='user_api_key_can_use_ia_model')


class AiUsageLog(Base):
    __tablename__ = 'ai_usage_log'
    __table_args__ = (
        ForeignKeyConstraint(['id_agent_model'], ['ai.agent_model.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='agent_model_fk'),
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='ia_usage_log_id'),
        {'schema': 'ai'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_agent_model: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_user: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    usage_details: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    agent_model: Mapped['AgentModel'] = relationship('AgentModel', back_populates='ai_usage_log')
    user: Mapped[Optional['User']] = relationship('User', back_populates='ai_usage_log')
