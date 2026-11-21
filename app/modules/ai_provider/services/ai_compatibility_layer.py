"""Provider-independent AI generation and structured response handling."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ....core.ai_endpoint import validate_ai_endpoint
from ....core.db_models.ai_models import (
    Agent,
    AgentModel,
    AiModel,
    SharedApiKey,
    UserApiKey,
    UserApiKeyCanUseIaModel,
)
from ....core.db_models.user_config_models import (
    Language,
    ResponseLanguagePreferenceOrder,
    UserGlobalConfig,
)
from ....core.security import decrypt, get_current_user
from ...ai.models import AgentModelFilters, AiUsageLogCreate
from ...ai.services import (
    create_ai_usage_log,
    get_provider,
    list_agent_models,
)
from ..models import (
    CreateEssayQuestionResponse,
    CreateFeynmanResponse,
    CreateFlashcard,
    CreateFlashcardGroup,
    CreateFlashcardsResponse,
    CreateMultipleChoiceQuestionResponse,
    CreateStudySessionResponse,
    EvaluateEssayQuestionResponse,
    EvaluateFeynmanResponse,
    EvaluateMultipleChoiceQuestionResponse,
    GenerateNodeDescription,
    ManipulateFlashcardGroup,
    ManipulateGraphResponse,
    ManipulateNodeResponse,
    SearchQueries,
    StudyAssistentResponse,
    StudyManagerResponse,
)

logger = logging.getLogger(__name__)

QUALITY_SCORES = {
    "unusable": 0.1,
    "poor": 1.0,
    "fair": 2.5,
    "good": 5.0,
    "very_good": 7.5,
    "excellent": 10.0,
}
AI_MODEL_REQUEST_TIMEOUT_SECONDS = 240
AI_MODEL_HTTP_TIMEOUT_SECONDS = AI_MODEL_REQUEST_TIMEOUT_SECONDS + 30

# Keep every planned task here. Some response classes are intentionally not
# defined yet and can be added to app.modules.ai_provider.models later.
TASK_RESPONSE_MODELS: dict[str, Any] = {
    "manipulate_graph": ManipulateGraphResponse,
    "recommend_study_resource": SearchQueries,
    "manipulate_node": ManipulateNodeResponse,
    "create_study_session": CreateStudySessionResponse,
    "evaluate_essay_question": EvaluateEssayQuestionResponse,
    "create_essay_question": CreateEssayQuestionResponse,
    "create_multiple_choice_question": CreateMultipleChoiceQuestionResponse,
    "evaluate_multiple_choice_question": EvaluateMultipleChoiceQuestionResponse,
    "create_feynman": CreateFeynmanResponse,
    "evaluate_feynman": EvaluateFeynmanResponse,
    "evaluate_feynman ": EvaluateFeynmanResponse,
    "create_flashcard": CreateFlashcard,
    "create_flashcardS": CreateFlashcardsResponse,
    "study_manager": StudyManagerResponse,
    "study_assistent": StudyAssistentResponse,
    "create_flashcard_group": CreateFlashcardGroup,
    "manipulate_flashcard_group": ManipulateFlashcardGroup,
    "create_flashcards": CreateFlashcardsResponse,
    "generate_node_description": GenerateNodeDescription
}


def _import_langchain() -> tuple[Any, Any]:
    """Import LangChain at request time so unrelated API routes can start."""
    try:
        chat_models = importlib.import_module("langchain.chat_models")
        prompts = importlib.import_module("langchain_core.prompts")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "AI generation requires the langchain and langchain-core packages."
        ) from exc
    return chat_models.init_chat_model, prompts.ChatPromptTemplate


def _format_provider_error(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "Timed out waiting for the model provider."
    message = str(error)
    if any(
        marker in message.casefold()
        for marker in (
            "tool_use_failed",
            "failed_generation",
            "failed to parse tool call arguments",
        )
    ):
        return "Provider rejected malformed structured-output arguments."
    return message


class AiProvider:
    """Generate structured responses using an agent's configured model order."""

    def __init__(self, db: Session, user_token: str):
        self.db = db
        self.user_token = user_token

    def _calculate_preference_order(
        self, agent_id: UUID, owner_id: UUID
    ) -> list[tuple[AiModel, float, AgentModel]]:
        agent_models = list_agent_models(
            db=self.db,
            filters=AgentModelFilters(id_agent=agent_id),
            owner_id=owner_id,
        )
        preference_order: list[tuple[AiModel, float, AgentModel]] = []

        model_ids = {agent_model.id_ai_model for agent_model in agent_models}
        models_by_id: dict[UUID, AiModel] = {}
        if model_ids:
            models_by_id = {
                model.id: model
                for model in self.db.scalars(
                    select(AiModel).where(AiModel.id.in_(model_ids))
                ).all()
            }

        for agent_model in agent_models:
            model = models_by_id.get(agent_model.id_ai_model)
            if model is None:
                raise RuntimeError(
                    f"AI model '{agent_model.id_ai_model}' could not be loaded."
                )
            quality = getattr(agent_model.quality_expected, "value", None)
            quality_score = QUALITY_SCORES.get(quality or "fair", 2.5)
            token_capacity = (model.input_token_limit or 0) + (
                model.output_token_limit or 0
            )
            preference_order.append(
                (model, quality_score * token_capacity, agent_model)
            )

        return sorted(preference_order, key=lambda item: item[1], reverse=True)

    @staticmethod
    def _get_response_model(task: Any) -> Any:
        """Resolve a task's response class while preserving future tasks."""
        task_name = getattr(task, "value", task)
        response_model = TASK_RESPONSE_MODELS.get(str(task_name))
        if response_model is None:
            supported = ", ".join(sorted(TASK_RESPONSE_MODELS))
            raise ValueError(
                f"Unsupported AI task '{task_name}'. Supported tasks: {supported}."
            )

        if isinstance(response_model, str):
            class_name = response_model
            response_model = globals().get(class_name)
        else:
            class_name = response_model.__name__

        if response_model is None or isinstance(response_model, str):
            raise NotImplementedError(
                f"The response model '{class_name}' for task '{task_name}' "
                "has not been implemented yet."
            )
        return response_model

    @staticmethod
    def _get_prompt_settings(
        agent: Any, agent_model: AgentModel
    ) -> tuple[str, float]:
        system_prompt = (
            agent_model.custom_system_prompt or agent.base_system_prompt
        )
        configured_temperature = (
            agent_model.custom_temperature
            if agent_model.custom_temperature is not None
            else agent.temperature
        )
        temperature = float(
            configured_temperature if configured_temperature is not None else 0.3
        )
        return system_prompt, temperature

    def _load_model_api_keys(
        self,
        owner_id: UUID,
        preference_order: Sequence[tuple[AiModel, float, AgentModel]],
    ) -> tuple[
        dict[UUID, list[UserApiKey]],
        dict[UUID, list[SharedApiKey]],
    ]:
        model_ids = {model.id for model, _, _ in preference_order}
        if not model_ids:
            return {}, {}

        personal_keys_by_model: dict[UUID, list[UserApiKey]] = {}
        personal_key_rows = self.db.execute(
            select(UserApiKeyCanUseIaModel.id_ai_model, UserApiKey)
            .join(
                UserApiKey,
                UserApiKey.id == UserApiKeyCanUseIaModel.id_user_api_key,
            )
            .join(AiModel, AiModel.id == UserApiKeyCanUseIaModel.id_ai_model)
            .where(
                UserApiKeyCanUseIaModel.id_ai_model.in_(model_ids),
                UserApiKey.id_user == owner_id,
                UserApiKey.is_active.is_(True),
                UserApiKey.id_ai_provider == AiModel.id_ai_provider,
            )
        ).all()
        for model_id, api_key in personal_key_rows:
            personal_keys_by_model.setdefault(model_id, []).append(api_key)

        shared_keys_by_model: dict[UUID, list[SharedApiKey]] = {}
        shared_key_rows = self.db.execute(
            select(AiModel.id, SharedApiKey)
            .join(
                SharedApiKey,
                SharedApiKey.id_ai_provider == AiModel.id_ai_provider,
            )
            .where(
                AiModel.id.in_(model_ids),
                SharedApiKey.is_active.is_(True),
            )
        ).all()
        for model_id, api_key in shared_key_rows:
            shared_keys_by_model.setdefault(model_id, []).append(api_key)

        return personal_keys_by_model, shared_keys_by_model

    def _get_response_language(self, user_id: UUID) -> str | None:
        preferred_language = self.db.scalar(
            select(Language.name)
            .join(
                ResponseLanguagePreferenceOrder,
                ResponseLanguagePreferenceOrder.id_language == Language.id,
            )
            .where(
                ResponseLanguagePreferenceOrder.id_user == user_id,
                ResponseLanguagePreferenceOrder.preference_order.is_not(None),
            )
            .order_by(
                ResponseLanguagePreferenceOrder.preference_order.asc().nulls_last(),
                Language.name,
            )
            .limit(1)
        )
        if preferred_language:
            return preferred_language

        return self.db.scalar(
            select(Language.name)
            .join(UserGlobalConfig, UserGlobalConfig.id_language == Language.id)
            .where(UserGlobalConfig.id_user == user_id)
            .limit(1)
        )

    async def _invoke_model(
        self,
        model: AiModel,
        api_keys: Sequence[UserApiKey | SharedApiKey],
        provider: Any,
        system_prompt: str,
        temperature: float,
        user_prompt: str,
        response_model: Any,
    ) -> tuple[Any, Any]:
        init_chat_model, chat_prompt_template = await asyncio.to_thread(
            _import_langchain
        )
        last_error: Exception | None = None
        attempt_errors: list[Exception] = []

        for api_key in api_keys:
            attempt_started = perf_counter()
            try:
                decrypted_key = decrypt(api_key.encrypted_key)
                if provider.protocol == "openai_compatible":
                    if not provider.base_url:
                        raise RuntimeError(
                            f"Provider '{provider.display_name}' has no base URL."
                        )
                    await asyncio.to_thread(
                        validate_ai_endpoint, provider.base_url
                    )
                    chat_model = init_chat_model(
                        model.slug,
                        model_provider="openai",
                        temperature=temperature,
                        api_key=decrypted_key or "local",
                        base_url=provider.base_url,
                        max_retries=0,
                        timeout=AI_MODEL_HTTP_TIMEOUT_SECONDS,
                    )
                else:
                    model_provider = (
                        "google_genai"
                        if provider.slug.casefold() == "google"
                        else provider.slug
                    )
                    client_options = (
                        {
                            "max_retries": 0,
                            "timeout": AI_MODEL_HTTP_TIMEOUT_SECONDS,
                        }
                        if model_provider in {"openai", "groq"}
                        else {}
                    )
                    chat_model = init_chat_model(
                        model.slug,
                        model_provider=model_provider,
                        temperature=temperature,
                        api_key=decrypted_key,
                        **client_options,
                    )
                structured_output_options: dict[str, str] = {}
                if model.slug.rsplit("/", 1)[-1].casefold().startswith(
                    "gpt-oss-"
                ):
                    structured_output_options["method"] = "json_mode"
                    system_prompt = (
                        f"{system_prompt}\n\n"
                        "Return only JSON matching the following JSON Schema:\n"
                        f"{json.dumps(response_model.model_json_schema(), ensure_ascii=False)}"
                    )
                structured_model = chat_model.with_structured_output(
                    response_model,
                    include_raw=True,
                    **structured_output_options,
                )
                prompt = chat_prompt_template.from_messages(
                    [
                        (
                            "system",
                            system_prompt.replace("{", "{{").replace("}", "}}"),
                        ),
                        ("human", "{user_prompt}"),
                    ]
                )
                structured_chain = prompt | structured_model
                result = await asyncio.wait_for(
                    structured_chain.ainvoke({"user_prompt": user_prompt}),
                    timeout=AI_MODEL_REQUEST_TIMEOUT_SECONDS,
                )
                try:
                    parsed, raw_response = self._parse_model_result(
                        result, response_model
                    )
                    logger.info(
                        "AI model %s completed in %.2fs.",
                        model.display_name,
                        perf_counter() - attempt_started,
                    )
                    return parsed, raw_response
                except ValueError as validation_error:
                    raw_text = (
                        self._extract_raw_text(result.get("raw"))
                        if isinstance(result, Mapping)
                        else None
                    )
                    correction_prompt = (
                        f"{user_prompt}\n\n"
                        "The previous response did not satisfy the required "
                        f"{response_model.__name__} data model. Correct the response "
                        "without changing its intended meaning. Include every required "
                        "field, use the expected types and allowed values, and return "
                        "only the corrected structured response.\n"
                        f"Validation issue: {str(validation_error)[:1500]}"
                    )
                    if raw_text:
                        correction_prompt += (
                            "\nPrevious response to correct:\n"
                            f"{raw_text[:3000]}"
                        )

                    corrected_result = await asyncio.wait_for(
                        structured_chain.ainvoke(
                            {"user_prompt": correction_prompt}
                        ),
                        timeout=AI_MODEL_REQUEST_TIMEOUT_SECONDS,
                    )
                    try:
                        parsed, raw_response = self._parse_model_result(
                            corrected_result, response_model
                        )
                        logger.info(
                            "AI model %s completed after response repair in %.2fs.",
                            model.display_name,
                            perf_counter() - attempt_started,
                        )
                        return parsed, raw_response
                    except ValueError as correction_error:
                        raise ValueError(
                            f"The response did not match "
                            f"{response_model.__name__} after one correction "
                            f"attempt: {correction_error}"
                        ) from correction_error
            except Exception as exc:
                last_error = exc
                attempt_errors.append(exc)
                logger.warning(
                    "AI model %s failed after %.2fs: %s",
                    model.display_name,
                    perf_counter() - attempt_started,
                    _format_provider_error(exc),
                )

        message = (
            f"All API keys for model '{model.display_name}' failed: "
            f"{_format_provider_error(last_error) if last_error else 'Unknown error.'}"
        )
        if attempt_errors and all(
            isinstance(error, TimeoutError) for error in attempt_errors
        ):
            raise TimeoutError(message) from last_error
        raise RuntimeError(message) from last_error

    def _parse_model_result(
        self, result: Any, response_model: Any
    ) -> tuple[Any, Any]:
        if not isinstance(result, Mapping):
            raise TypeError("The AI provider returned an invalid response.")

        raw_response = result.get("raw")
        parsed = result.get("parsed")
        validation_errors: list[str] = []
        if parsed is not None:
            try:
                return response_model.model_validate(parsed), raw_response
            except ValidationError as exc:
                validation_errors.append(self._format_validation_error(exc))

        raw_text = self._extract_raw_text(raw_response)
        if raw_text:
            try:
                return self._try_recover_response(raw_text, response_model), raw_response
            except (TypeError, ValueError) as exc:
                validation_errors.append(str(exc))

        details = "; ".join(error for error in validation_errors if error)
        if not details:
            details = "No structured data or readable raw response was returned."
        raise ValueError(
            f"The response does not match {response_model.__name__}: {details}"
        )

    @staticmethod
    def _format_validation_error(error: ValidationError) -> str:
        issues = error.errors(include_input=False)
        return "; ".join(
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in issues
        )

    @staticmethod
    def _extract_raw_text(raw_response: Any) -> str | None:
        content = getattr(raw_response, "content", raw_response)
        if isinstance(content, str):
            return content or None
        if isinstance(content, Mapping):
            for key in ("text", "input", "args", "arguments"):
                value = content.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, (Mapping, list)):
                    return json.dumps(value, ensure_ascii=False, default=str)
            return json.dumps(content, ensure_ascii=False, default=str)
        if isinstance(content, Sequence):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, Mapping):
                    for key in ("text", "input", "args", "arguments"):
                        value = part.get(key)
                        if isinstance(value, str):
                            text_parts.append(value)
                            break
                        if isinstance(value, (Mapping, list)):
                            text_parts.append(
                                json.dumps(value, ensure_ascii=False, default=str)
                            )
                            break
            if text_parts:
                return "\n".join(text_parts)

        tool_calls = getattr(raw_response, "tool_calls", None)
        if tool_calls:
            return json.dumps(
                {"tool_calls": [{"function": {"arguments": call.get("args")}}
                                for call in tool_calls]},
                ensure_ascii=False,
                default=str,
            )
        return None

    def _try_recover_response(self, raw_response: Any, response_model: Any) -> Any:
        """Recover malformed structured output when the provider returned text."""
        if not isinstance(raw_response, str):
            raise TypeError("The failed AI response was not text.")
        from .jsonServices import JsonHelper

        return JsonHelper()._parse_model_response(raw_response, response_model)

    def _record_usage(self, agent_model: AgentModel, raw_response: Any) -> None:
        user = get_current_user(token=self.user_token, db=self.db)
        response_metadata = getattr(raw_response, "response_metadata", {}) or {}
        usage_metadata = getattr(raw_response, "usage_metadata", {}) or {}
        create_ai_usage_log(
            AiUsageLogCreate(
                id_agent_model=agent_model.id,
                id_user=user.id,
                usage_details={
                    "response_metadata": response_metadata,
                    "usage_metadata": usage_metadata,
                },
            ),
            self.db,
            self.user_token,
        )

    def _prepare_call_context(
        self,
        agent_id: UUID,
        response_language: str | None,
    ) -> tuple[
        UUID,
        Agent,
        Any,
        list[tuple[AiModel, float, AgentModel]],
        str | None,
        dict[UUID, list[UserApiKey]],
        dict[UUID, list[SharedApiKey]],
    ]:
        try:
            user = get_current_user(token=self.user_token, db=self.db)
            agent = self.db.scalar(
                select(Agent).where(
                    Agent.id == agent_id,
                    or_(Agent.id_user.is_(None), Agent.id_user == user.id),
                    Agent.is_active.is_(True),
                )
            )
            if agent is None:
                raise RuntimeError("Agent not found.")

            response_model = self._get_response_model(agent.task)
            preference_order = self._calculate_preference_order(agent_id, user.id)
            personal_keys_by_model, shared_keys_by_model = (
                self._load_model_api_keys(user.id, preference_order)
            )
            response_language = response_language or self._get_response_language(user.id)
            self.db.commit()
            return (
                user.id,
                agent,
                response_model,
                preference_order,
                response_language,
                personal_keys_by_model,
                shared_keys_by_model,
            )
        except Exception:
            self.db.rollback()
            raise

    def _prepare_model_attempt(
        self,
        model: AiModel,
        agent: Agent,
        agent_model: AgentModel,
        owner_id: UUID,
        api_keys: Sequence[UserApiKey | SharedApiKey],
    ) -> tuple[Sequence[UserApiKey | SharedApiKey], Any, str, float] | None:
        try:
            provider = get_provider(
                db=self.db,
                identificator=str(model.id_ai_provider),
                owner_id=owner_id,
            )
            if model.is_active is False or provider.is_active is False:
                self.db.commit()
                return None

            system_prompt, temperature = self._get_prompt_settings(
                agent, agent_model
            )
            self.db.commit()
            return api_keys, provider, system_prompt, temperature
        except Exception:
            self.db.rollback()
            raise

    async def call_ai(
        self,
        user_prompt: str,
        agent_id: UUID,
        response_language: str | None = None,
    ) -> Any:
        """Call configured models in preference order with explicit fallbacks."""
        if not user_prompt.strip():
            raise ValueError("The user prompt cannot be empty.")

        (
            owner_id,
            agent,
            response_model,
            preference_order,
            response_language,
            personal_keys_by_model,
            shared_keys_by_model,
        ) = await run_in_threadpool(
            self._prepare_call_context,
            agent_id,
            response_language,
        )
        if preference_order and not any(
            personal_keys_by_model.values()
        ) and not any(shared_keys_by_model.values()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "No active API keys are configured for any model of this agent."
                ),
            )

        failures: list[str] = []
        failure_errors: list[Exception] = []
        model_names = {
            id(model): model.display_name
            for model, _, _ in preference_order
        }

        for key_source in ("personal", "shared"):
            keys_by_model = (
                personal_keys_by_model
                if key_source == "personal"
                else shared_keys_by_model
            )
            for model, _, agent_model in preference_order:
                api_keys = keys_by_model.get(model.id, [])
                if not api_keys:
                    continue
                try:
                    attempt = await run_in_threadpool(
                        self._prepare_model_attempt,
                        model,
                        agent,
                        agent_model,
                        owner_id,
                        api_keys,
                    )
                    if attempt is None:
                        continue
                    api_keys, provider, system_prompt, temperature = attempt
                    if response_language:
                        system_prompt = (
                            f"{system_prompt}\n\n"
                            f"Respond in {response_language}. Keep all natural-language "
                            "content in that language, but do not translate JSON keys, "
                            "code identifiers, or fixed enum values required by the schema."
                        )
                    parsed, raw_response = await self._invoke_model(
                        model,
                        api_keys,
                        provider,
                        system_prompt,
                        temperature,
                        user_prompt,
                        response_model,
                    )
                    await run_in_threadpool(
                        self._record_usage, agent_model, raw_response
                    )
                    return parsed
                except Exception as exc:
                    failures.append(
                        f"{model_names[id(model)]} ({key_source} keys): {exc}"
                    )
                    failure_errors.append(exc)
                    logger.warning(
                        "Configured AI model failed for agent %s.",
                        agent_id,
                        exc_info=True,
                    )

        if not failures:
            raise RuntimeError(f"No models are configured for agent '{agent_id}'.")
        if all(isinstance(error, TimeoutError) for error in failure_errors):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI generation timed out for every configured model.",
            )
        raise RuntimeError(
            "AI generation failed for every configured model: "
            + " | ".join(failures)
        )
