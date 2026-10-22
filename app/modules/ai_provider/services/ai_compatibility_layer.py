"""Provider-independent AI generation and structured response handling."""

from __future__ import annotations

import logging
import importlib
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ....core.db_models.ai_models import AgentModel, AiModel, UserApiKey
from ....core.security import decrypt, get_current_user
from ...ai.models import AgentModelFilters, AiUsageLogCreate
from ...ai.services import (
    create_ai_usage_log,
    get_agent,
    get_ai_model,
    get_provider,
    get_user_api_key,
    list_agent_models,
    list_user_api_key_can_use_ia_model,
)
from ..models import (
    CreateEssayQuestionResponse,
    CreateStudySessionResponse,
    EvaluateEssayQuestionResponse,
    EvaluateFeynmanResponse,
    ManipulateGraphResponse,
    ManipulateNodeResponse,
    SearchQueries,
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

# Keep every planned task here. Some response classes are intentionally not
# defined yet and can be added to app.modules.ai_provider.models later.
TASK_RESPONSE_MODELS: dict[str, Any] = {
    "manipulate_graph": ManipulateGraphResponse,
    "recommend_study_resource": SearchQueries,
    "manipulate_node": ManipulateNodeResponse,
    "create_study_session": CreateStudySessionResponse,
    "evaluate_essay_question": EvaluateEssayQuestionResponse,
    "create_essay_question": CreateEssayQuestionResponse,
    "create_multiple_choice_question": "CreateMultipleChoiceQuestionResponse",
    "evaluate_multiple_choice_question": "EvaluateMultipleChoiceQuestionResponse",
    "create_feynman": "CreateFeynmanResponse",
    "evaluate_feynman": EvaluateFeynmanResponse,
    "create_flashcard": "CreateFlashcard",
    "study_manager": "StudyManagerResponse",
    "study_assistent": "studyAssistentResponse",
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


class AiProvider:
    """Generate structured responses using an agent's configured model order."""

    def __init__(self, db: Session, user_token: str):
        self.db = db
        self.user_token = user_token

    def _calculate_preference_order(
        self, agent_id: UUID
    ) -> list[tuple[AiModel, float, AgentModel]]:
        agent_models = list_agent_models(
            db=self.db,
            filters=AgentModelFilters(id_agent=agent_id),
        )
        preference_order: list[tuple[AiModel, float, AgentModel]] = []

        for agent_model in agent_models:
            model = get_ai_model(
                identificator=str(agent_model.id_ai_model),
                db=self.db,
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
            raise RuntimeError(
                f"No API key is configured for model '{model.display_name}'."
            )

        keys: list[UserApiKey] = []
        for link in links:
            try:
                keys.append(
                    get_user_api_key(
                        token=self.user_token,
                        identificator=str(link.id_user_api_key),
                        db=self.db,
                    )
                )
            except Exception:
                logger.warning(
                    "Unable to load an API key for model %s.",
                    model.display_name,
                    exc_info=True,
                )
        if not keys:
            raise RuntimeError(
                f"All configured API keys for model '{model.display_name}' "
                "could not be loaded."
            )
        return keys

    async def _invoke_model(
        self,
        model: AiModel,
        provider: Any,
        system_prompt: str,
        temperature: float,
        user_prompt: str,
        response_model: Any,
    ) -> tuple[Any, Any]:
        init_chat_model, chat_prompt_template = _import_langchain()
        last_error: Exception | None = None

        for api_key in self._get_api_keys(model):
            try:
                chat_model = init_chat_model(
                    model.slug,
                    model_provider=provider.slug,
                    temperature=temperature,
                    api_key=decrypt(api_key.encrypted_key),
                )
                structured_model = chat_model.with_structured_output(
                    response_model,
                    include_raw=True,
                )
                prompt = chat_prompt_template.from_messages(
                    [
                        ("system", system_prompt),
                        ("human", "{user_prompt}"),
                    ]
                )
                result = await (prompt | structured_model).ainvoke(
                    {"user_prompt": user_prompt}
                )
                if not isinstance(result, Mapping):
                    raise ValueError("The AI provider returned an invalid response.")

                parsed = result.get("parsed")
                raw_response = result.get("raw")
                if parsed is None:
                    raw_content = getattr(raw_response, "content", raw_response)
                    parsed = self._try_recover_response(
                        raw_content,
                        response_model,
                    )
                return parsed, raw_response
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "AI request failed for model %s; trying another key.",
                    model.display_name,
                    exc_info=True,
                )

        raise RuntimeError(
            f"All API keys for model '{model.display_name}' failed."
        ) from last_error

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

    async def call_ai(self, user_prompt: str, agent_id: UUID) -> Any:
        """Call configured models in preference order with explicit fallbacks."""
        if not user_prompt.strip():
            raise ValueError("The user prompt cannot be empty.")

        agent = get_agent(str(agent_id), self.db)
        response_model = self._get_response_model(agent.task)
        failures: list[str] = []

        for model, _, agent_model in self._calculate_preference_order(agent_id):
            try:
                provider = get_provider(
                    db=self.db,
                    identificator=str(model.id_ai_provider),
                )
                system_prompt, temperature = self._get_prompt_settings(
                    agent, agent_model
                )
                parsed, raw_response = await self._invoke_model(
                    model,
                    provider,
                    system_prompt,
                    temperature,
                    user_prompt,
                    response_model,
                )
                self._record_usage(agent_model, raw_response)
                return parsed
            except Exception as exc:
                failures.append(f"{model.display_name}: {exc}")
                logger.warning(
                    "Configured AI model failed for agent %s.",
                    agent_id,
                    exc_info=True,
                )

        if not failures:
            raise RuntimeError(f"No models are configured for agent '{agent_id}'.")
        raise RuntimeError(
            "AI generation failed for every configured model: "
            + " | ".join(failures)
        )
