import pytest
from pydantic import ValidationError

from app.modules.ai_provider.models import (
    CreateFlashcardsResponse,
    CreateMultipleChoiceQuestionResponse,
)
from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider


def _choice(is_correct: bool, **extra):
    return {
        "is_correct": is_correct,
        "statement": "Alternativa",
        "explanation": "Explicação",
        **extra,
    }


def test_multiple_choice_contract_uses_app_field_names_and_accepts_legacy_data():
    response = CreateMultipleChoiceQuestionResponse.model_validate(
        {
            "title": "Questão",
            "statement": "Enunciado",
            "choises": [
                _choice(True, weigth=2),
                _choice(False, weight=1),
                _choice(False, weight=1),
                _choice(False, weight=1),
            ],
        }
    )

    assert response.model_dump()["choices"][0]["weight"] == 2
    schema = CreateMultipleChoiceQuestionResponse.model_json_schema()
    assert "choices" in schema["properties"]
    assert "choises" not in schema["properties"]
    assert "weight" in schema["$defs"]["Choise"]["properties"]
    assert "weigth" not in schema["$defs"]["Choise"]["properties"]


def test_multiple_choice_contract_rejects_too_few_or_multiple_correct_choices():
    with pytest.raises(ValidationError):
        CreateMultipleChoiceQuestionResponse.model_validate(
            {
                "title": "Questão",
                "statement": "Enunciado",
                "choices": [_choice(True, weight=1), _choice(False, weight=1)],
            }
        )
    with pytest.raises(ValidationError):
        CreateMultipleChoiceQuestionResponse.model_validate(
            {
                "title": "Questão",
                "statement": "Enunciado",
                "choices": [
                    _choice(True, weight=1),
                    _choice(True, weight=1),
                    _choice(False, weight=1),
                    _choice(False, weight=1),
                ],
            }
        )


def test_flashcards_task_returns_the_list_shape_consumed_by_the_app():
    response_model = AiProvider._get_response_model("create_flashcards")
    response = response_model.model_validate(
        {
            "flashcards": [
                {
                    "title": "O que é uma célula?",
                    "statement": "A unidade básica dos seres vivos.",
                    "target_skill": "memória",
                }
            ]
        }
    )

    assert response_model is CreateFlashcardsResponse
    assert response.model_dump()["flashcards"][0]["target_skill"] == "memória"
