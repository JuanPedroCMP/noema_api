"""Provider-independent AI generation and structured response handling."""

from __future__ import annotations

import logging
import importlib
import asyncio
import json
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ....core.ai_endpoint import validate_ai_endpoint
from ....core.db_models.ai_models import (
    Agent,
    AgentModel,
    AiModel,
    SharedApiKey,
    UserApiKey,
)
from ....core.security import decrypt, get_current_user
from ....core.db_models.user_config_models import (
    Language,
    ResponseLanguagePreferenceOrder,
    UserGlobalConfig,
)
from ...ai.models import AgentModelFilters, AiUsageLogCreate
from ...ai.services import (
    create_ai_usage_log,
    get_ai_model,
    get_provider,
    get_user_api_key,
    list_agent_models,
    list_user_api_key_can_use_ia_model,
)
from ..models import (
    CreateEssayQuestionResponse,
    CreateFlashcard,
    CreateFlashcardGroup,
    CreateFlashcardsResponse,
    CreateFeynmanResponse,
    CreateMultipleChoiceQuestionResponse,
    CreateStudySessionResponse,
    EvaluateEssayQuestionResponse,
    EvaluateFeynmanResponse,
    EvaluateMultipleChoiceQuestionResponse,
    GenerateNodeDescription,
    ManipulateGraphResponse,
    ManipulateFlashcardGroup,
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
AI_MODEL_REQUEST_TIMEOUT_SECONDS = 30
AI_MODEL_HTTP_TIMEOUT_SECONDS = 28

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

        for agent_model in agent_models:
            model = get_ai_model(
                identificator=str(agent_model.id_ai_model),
                db=self.db,
                owner_id=owner_id,
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

    def _get_api_keys(self, model: AiModel) -> list[UserApiKey]:
        links = list_user_api_key_can_use_ia_model(
            db=self.db,
            filters={"id_ai_model": model.id},
            token=self.user_token,
        )
        if not links:
            return []

        keys: list[UserApiKey] = []
        for link in links:
            try:
                key = get_user_api_key(
                    token=self.user_token,
                    identificator=str(link.id_user_api_key),
                    db=self.db,
                )
                if key.is_active:
                    keys.append(key)
            except Exception:
                logger.warning(
                    "Unable to load an API key for model %s.",
                    model.display_name,
                    exc_info=True,
                )
        return keys

    def _get_shared_api_keys(self, model: AiModel) -> list[SharedApiKey]:
        return list(
            self.db.scalars(
                select(SharedApiKey).where(
                    SharedApiKey.id_ai_provider == model.id_ai_provider,
                    SharedApiKey.is_active.is_(True),
                )
            ).all()
        )

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
        init_chat_model, chat_prompt_template = _import_langchain()
        last_error: Exception | None = None

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
                        ("system", system_prompt),
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
                logger.warning(
                    "AI model %s failed after %.2fs: %s",
                    model.display_name,
                    perf_counter() - attempt_started,
                    _format_provider_error(exc),
                )

        raise RuntimeError(
            f"All API keys for model '{model.display_name}' failed: "
            f"{_format_provider_error(last_error) if last_error else 'Unknown error.'}"
        ) from last_error

    def _parse_model_result(
        self, result: Any, response_model: Any
    ) -> tuple[Any, Any]:
        if not isinstance(result, Mapping):
            raise ValueError("The AI provider returned an invalid response.")

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
            raise ValueError("The failed AI response was not text.")
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

    async def call_ai(
        self,
        user_prompt: str,
        agent_id: UUID,
        response_language: str | None = None,
    ) -> Any:
        """Call configured models in preference order with explicit fallbacks."""
        if not user_prompt.strip():
            raise ValueError("The user prompt cannot be empty.")

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
        failures: list[str] = []
        preference_order = self._calculate_preference_order(agent_id, user.id)
        has_configured_keys = False
        response_language = response_language or self._get_response_language(user.id)

        for key_source in ("personal", "shared"):
            for model, _, agent_model in preference_order:
                try:
                    api_keys = (
                        self._get_api_keys(model)
                        if key_source == "personal"
                        else self._get_shared_api_keys(model)
                    )
                    if not api_keys:
                        continue
                    has_configured_keys = True

                    provider = get_provider(
                        db=self.db,
                        identificator=str(model.id_ai_provider),
                        owner_id=user.id,
                    )
                    if model.is_active is False or provider.is_active is False:
                        continue
                    system_prompt, temperature = self._get_prompt_settings(
                        agent, agent_model
                    )
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
                    self._record_usage(agent_model, raw_response)
                    return parsed
                except Exception as exc:
                    failures.append(f"{model.display_name} ({key_source} keys): {exc}")
                    logger.warning(
                        "Configured AI model failed for agent %s.",
                        agent_id,
                        exc_info=True,
                    )

        if not failures:
            if preference_order and not has_configured_keys:
                raise RuntimeError(
                    f"No active API keys are configured for any model of agent '{agent_id}'."
                )
            raise RuntimeError(f"No models are configured for agent '{agent_id}'.")
        raise RuntimeError(
            "AI generation failed for every configured model: "
            + " | ".join(failures)
        )
