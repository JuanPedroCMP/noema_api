from pydantic import ValidationError
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser, PydanticOutputParser
from langchain_core.runnables import RunnableLambda
from ..ai.services import list_agent_models, get_ai_model, get_agent, get_provider
from ...core.db_models.ai_models import AgentModel, AiModel
from ..ai.models import AgentModelFilters
from sqlalchemy.orm import Session
from .models import AiGraphResponse
from uuid import UUID
from ..ai.services import create_ai_usage_log
from ..ai.models import AiUsageLogCreate
from ..auth.service import get_current_user
import json  
import groq
import re
import json
import re
from typing import Any
from json_repair import loads as repair_json_loads
from pydantic import BaseModel, ValidationError

### Fazer duas chamadas: uma para criar os nodes e outra para as relações, para evitar erros em grafos grandes. Tambpem arrumar outras formas de economizar tokens

class AiProvider:
    def __init__(self, db: Session, user_token: str):
        self.db = db
        self.user_token = user_token
        
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
        text = AiProvider._strip_markdown(text)

        if not text:
            return []

        candidates: list[str] = [text]

        # JSON que esteja no meio de texto.
        candidates.extend(
            AiProvider._extract_balanced_json(text)
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

        for candidate in AiProvider._normalize_candidates(text):

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
                    return AiProvider._decode_json(arguments)

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
                        return AiProvider._decode_json(arguments)

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
                        return AiProvider._decode_json(arguments)

        return data

    @staticmethod
    def _parse_model_response(
        text: str,
        schema: type[BaseModel],
    ) -> BaseModel:

        data = AiProvider._decode_json(text)

        arguments = AiProvider._extract_arguments(data)

        # Corrige inconsistências conhecidas da IA
        arguments = AiProvider._normalize_graph_types(arguments)

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
        
    # TODO Cálculo da ordem de preferÊncia
    def _calculate_preference_order(self, agent_id: UUID) -> (list[tuple[AiModel, float, AgentModel]]):
        agents_models: list[AgentModel]  = list_agent_models(db=self.db, filters=AgentModelFilters(id_agent=agent_id))
        
        preference_order: list[tuple[AiModel, float]] = []
        
        quality_score = {
            "unusable": 0.1 ,
            "poor": 1,
            "fair": 2.5,    
            "good": 5,
            "very_good": 7.5,
            "excellent": 10,
        }
        
        for agent_model in agents_models:
            score_1 = quality_score.get(agent_model.quality_expected)
            model : AiModel = get_ai_model(identificator=str(agent_model.id_ai_model), db=self.db)
                        
            final_score = score_1 * (model.input_token_limit + model.output_token_limit)
            print(f"{model.display_name}: {final_score}")
            preference = (model, final_score, agent_model)
            preference_order.append(preference)
        
        return preference_order     

    # TODO Separar modelos que a api key pode utilizar
    
    # TODO Fazer chain
    def call_ai(self, user_prompt: str, agent_id: UUID):     
        preference_order = self._calculate_preference_order(agent_id=agent_id)
        preference_order.sort(key=lambda x: x[1], reverse=True)
        agent = get_agent(str(agent_id), self.db)
        
        for agent_model in preference_order:
            try:
                model = agent_model[0]
                
                ai_provider = get_provider(db=self.db, identificator=str(model.ai_provider.id))
                
                # agent_model = list_agent_models(db=self.db, filters=AgentModelFilters(id_agent=agent_id, ))
                
                system_prompt = ''
                if agent_model[2].custom_system_prompt == None or agent_model[2].custom_system_prompt == '':
                    system_prompt = agent.base_system_prompt
                else:
                    system_prompt = agent_model[2].custom_system_prompt
                    
                
                temperature = 0.3
                if agent_model[2].custom_system_prompt == None or agent_model[2].custom_system_prompt == 0:
                    temperature = agent.temperature
                else:
                    temperature = agent_model[2].custom_temperature
                
                model = init_chat_model(model.slug, model_provider=ai_provider.slug, temperature=temperature, api_key="")

                model_struc = model.with_structured_output(AiGraphResponse, include_raw=True,)

                prompt = ChatPromptTemplate.from_messages({
                    ("system", system_prompt),
                    ("human", "{user_prompt}"),
                })
                
                parser = PydanticOutputParser(pydantic_object=AiGraphResponse)
                print(1)
                chain = (prompt | model_struc)
                print(2)
                resultado = chain.invoke({"user_prompt": user_prompt})
                print(3)
                raw: dict = resultado["raw"]
                parsed: AiGraphResponse = resultado["parsed"]
                print(4)
                print("///////////////////////////////////////////////\nparsed\n//////////////////////////////////////////////\n")
                print(parsed.model_dump_json())
                print(type(parsed.model_dump_json()))
                
                print("///////////////////////////////////////////////\nusage_metadata\n//////////////////////////////////////////////\n")
                print(raw.usage_metadata)
                print(type(raw.usage_metadata))
                
                
                print("///////////////////////////////////////////////\nresponse_metadata\n//////////////////////////////////////////////\n")              
                print(json.dumps(raw.response_metadata))
                print(type(json.dumps(raw.response_metadata)))
                
                print(self.user_token)
                print(agent_model[2].id)
                print(type(agent_model[2].id))
                
                user = get_current_user(token=self.user_token, db=self.db)
                
                
                create_ai_usage_log(AiUsageLogCreate(
                    id_agent_model= str(agent_model[2].id),
                    id_user=user.id,
                    usage_details=raw.response_metadata,
                ), self.db, self.user_token)
                return resultado
            
            except groq.BadRequestError as e:
                error = e.body.get("error", {})

                if error.get("code") == "tool_use_failed":
                    failed_generation = error.get("failed_generation")
                    try:
                        parsed = self._parse_model_response(
                            failed_generation,
                            AiGraphResponse,
                        )

                        print("JSON recuperado com sucesso:")
                        print(parsed.model_dump_json(indent=2))
                        return parsed.model_dump_json(indent=2)

                    except ValueError as exc:
                        print("Falha ao recuperar resposta da IA:")
                        print(exc)

                        # Aqui você decide:
                        # - tentar outro modelo
                        # - fazer uma segunda chamada de correção
                        # - registrar o erro
                        # - abortar
                        raise
                    continue

                raise
                print(f"err: {e}")
                
                print(type(e))
                print(repr(e))
                print(e.__dict__)
                
                    

