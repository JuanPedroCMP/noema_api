from pydantic import ValidationError
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser, PydanticOutputParser
from langchain_core.runnables import RunnableLambda
from ...ai.services import list_agent_models, get_ai_model, get_agent, get_provider
from ....core.db_models.ai_models import AgentModel, AiModel, AiProvider
from ...ai.models import AgentModelFilters
from sqlalchemy.orm import Session
from ..models import ManipulateGraphResponse
from uuid import UUID
from ...ai.services import create_ai_usage_log
from ...ai.models import AiUsageLogCreate
from ...auth.service import get_current_user
import json  
import groq
import re
import json
import re
from typing import Any
from json_repair import loads as repair_json_loads
from pydantic import BaseModel, ValidationError

class JsonHelper:
    ## Gerado com AI  
    @staticmethod
    def _normalize_graph_types(data: Any) -> Any:
        """
        Normaliza valores de type dos nodes antes da validação Pydantic.

        Correções conhecidas:
            SUBTOPIC -> CONCEPT

        Não altera outros valores inválidos, permitindo que o Pydantic
        continue detectando erros reais.
        """

        if not isinstance(data, dict):
            return data

        nodes = data.get("nodes")

        if not isinstance(nodes, list):
            return data

        for node in nodes:
            if not isinstance(node, dict):
                continue

            node_type = node.get("type")

            if not isinstance(node_type, str):
                continue

            normalized_type = node_type.strip().upper()

            if normalized_type == "SUBTOPIC":
                node["type"] = "CONCEPT"

        return data

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """
        Remove wrappers comuns que modelos usam ao retornar JSON.
        Não tenta corrigir o JSON aqui.
        """
        if not text:
            return ""

        text = text.strip()

        # BOM
        text = text.lstrip("\ufeff")

        # ```json ... ```
        fenced = re.search(
            r"```(?:json|javascript|js)?\s*(.*?)```",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if fenced:
            text = fenced.group(1).strip()

        return text

    @staticmethod
    def _extract_balanced_json(text: str) -> list[str]:
        """
        Extrai objetos/arrays JSON do meio de uma resposta que pode conter
        texto antes/depois.

        Exemplo:
            "Aqui está: {\"foo\": 1} espero que ajude"

        retorna:
            ['{"foo": 1}']

        Também respeita strings, escapes e objetos aninhados.
        """
        candidates: list[str] = []

        start: int | None = None
        stack: list[str] = []

        in_string = False
        quote = ""
        escaped = False

        for i, char in enumerate(text):
            # ---------------------------------------------------------
            # Dentro de string
            # ---------------------------------------------------------
            if in_string:
                if escaped:
                    escaped = False
                    continue

                if char == "\\":
                    escaped = True
                    continue

                if char == quote:
                    in_string = False

                continue

            # ---------------------------------------------------------
            # Início de string
            # ---------------------------------------------------------
            if char in ('"', "'"):
                in_string = True
                quote = char
                continue

            # ---------------------------------------------------------
            # Abertura
            # ---------------------------------------------------------
            if char == "{":
                if not stack:
                    start = i

                stack.append("}")

                continue

            if char == "[":
                if not stack:
                    start = i

                stack.append("]")

                continue

            # ---------------------------------------------------------
            # Fechamento
            # ---------------------------------------------------------
            if char in ("}", "]"):
                if not stack:
                    continue

                # Estrutura incompatível.
                if stack[-1] != char:
                    continue

                stack.pop()

                # Estrutura completa.
                if not stack and start is not None:
                    candidate = text[start:i + 1].strip()

                    if candidate:
                        candidates.append(candidate)

                    start = None

        return candidates

    @staticmethod
    def _normalize_candidates(text: str) -> list[str]:
        """
        Gera diferentes candidatos para aumentar a tolerância sem
        alterar agressivamente o conteúdo original.
        """
        text = JsonHelper._strip_markdown(text)

        if not text:
            return []

        candidates: list[str] = [text]

        # JSON que esteja no meio de texto.
        candidates.extend(
            JsonHelper._extract_balanced_json(text)
        )

        # Remove wrappers comuns de tool/function calling.
        stripped = text.strip()

        if stripped.startswith("arguments"):
            colon = stripped.find(":")

            if colon != -1:
                candidates.append(
                    stripped[colon + 1:].strip()
                )

        # Remove callback style:
        # callback({...})
        callback_match = re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*\s*\((.*)\)\s*$",
            stripped,
            flags=re.DOTALL,
        )

        if callback_match:
            candidates.append(
                callback_match.group(1).strip()
            )

        # Remove duplicados mantendo ordem.
        unique: list[str] = []
        seen: set[str] = set()

        for candidate in candidates:
            if not candidate:
                continue

            if candidate in seen:
                continue

            seen.add(candidate)
            unique.append(candidate)

        return unique

    @staticmethod
    def _decode_json(text: str) -> Any:
        """
        Tenta converter texto potencialmente inválido para Python.

        Ordem:

        1. JSON estrito
        2. json-repair
        3. JSON reparado novamente de forma explícita

        Levanta ValueError somente depois de todas as tentativas.
        """
        errors: list[Exception] = []

        for candidate in JsonHelper._normalize_candidates(text):

            # =========================================================
            # 1. JSON estrito
            # =========================================================
            try:
                return json.loads(candidate)

            except json.JSONDecodeError as exc:
                errors.append(exc)

            # =========================================================
            # 2. JSON repair
            # =========================================================
            try:
                repaired = repair_json_loads(candidate)

                if repaired is not None:
                    return repaired

            except Exception as exc:
                errors.append(exc)

        message = (
            "Não foi possível converter a resposta do modelo para JSON.\n"
            f"Resposta recebida:\n{text[:4000]}\n"
            f"Tentativas realizadas: {len(errors)}"
        )

        raise ValueError(message) from (
            errors[-1] if errors else None
        )

    @staticmethod
    def _extract_arguments(data: Any) -> Any:
        """
        Localiza o payload real dentro de diferentes formatos de
        tool calling.

        Aceita:

            {"arguments": {...}}

            {"function": {"arguments": {...}}}

            {"tool_calls": [...]}

            {...payload direto...}
        """

        if not isinstance(data, (dict, list)):
            return data

        # -------------------------------------------------------------
        # Caso direto:
        #
        # {
        #   "arguments": {...}
        # }
        # -------------------------------------------------------------
        if isinstance(data, dict):

            if "arguments" in data:
                arguments = data["arguments"]

                # arguments já é objeto
                if isinstance(arguments, (dict, list)):
                    return arguments

                # arguments veio como string JSON
                if isinstance(arguments, str):
                    return JsonHelper._decode_json(arguments)

            # ---------------------------------------------------------
            # OpenAI/Groq style:
            #
            # {
            #   "function": {
            #       "arguments": {...}
            #   }
            # }
            # ---------------------------------------------------------
            function = data.get("function")

            if isinstance(function, dict):
                if "arguments" in function:
                    arguments = function["arguments"]

                    if isinstance(arguments, (dict, list)):
                        return arguments

                    if isinstance(arguments, str):
                        return JsonHelper._decode_json(arguments)

            # ---------------------------------------------------------
            # tool_calls
            # ---------------------------------------------------------
            tool_calls = data.get("tool_calls")

            if isinstance(tool_calls, list):

                for tool_call in tool_calls:

                    if not isinstance(tool_call, dict):
                        continue

                    function = tool_call.get("function")

                    if not isinstance(function, dict):
                        continue

                    arguments = function.get("arguments")

                    if isinstance(arguments, (dict, list)):
                        return arguments

                    if isinstance(arguments, str):
                        return JsonHelper._decode_json(arguments)

        return data

    @staticmethod
    def _parse_model_response(
        text: str,
        schema: type[BaseModel],
    ) -> BaseModel:

        data = JsonHelper._decode_json(text)

        arguments = JsonHelper._extract_arguments(data)

        # Corrige inconsistências conhecidas da IA
        arguments = JsonHelper._normalize_graph_types(arguments)

        try:
            return schema.model_validate(arguments)

        except ValidationError as exc:

            raise ValueError(
                "O JSON foi recuperado, mas não corresponde ao schema "
                f"{schema.__name__}.\n"
                f"Dados recuperados:\n"
                f"{json.dumps(arguments, ensure_ascii=False, indent=2)}\n"
                f"Erros de validação:\n{exc}"
            ) from exc
        