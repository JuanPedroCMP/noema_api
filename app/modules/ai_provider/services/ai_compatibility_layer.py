from pydantic import ValidationError
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser, PydanticOutputParser
from langchain_core.runnables import RunnableLambda
from ...ai.services import list_agent_models, get_ai_model, get_agent, get_provider, get_user_api_key, get_user_api_key_can_use_ia_model, list_user_api_key_can_use_ia_model
from ....core.db_models.ai_models import AgentModel, AiModel, UserApiKey, UserApiKeyCanUseIaModel
from ...ai.models import AgentModelFilters
from sqlalchemy.orm import Session
from ..models import ManipulateGraphResponse
from uuid import UUID
from ...ai.services import create_ai_usage_log
from ...ai.models import AiUsageLogCreate, UserApiKeyCanUseIaModelFilters
from ...auth.service import get_current_user
import json  
import groq
import re
import json
import re
from typing import Any
from json_repair import loads as repair_json_loads
from pydantic import BaseModel, ValidationError
from .services import JsonHelper 
from app.core.security import decrypt

### Fazer duas chamadas: uma para criar os nodes e outra para as relações, para evitar erros em grafos grandes. Tambpem arrumar outras formas de economizar tokens

class AiProvider:
    def __init__(self, db: Session, user_token: str):
        self.db = db
        self.user_token = user_token
        
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
    
    def call_ai(self, user_prompt: str, agent_id: UUID) -> str:     
        preference_order = self._calculate_preference_order(agent_id=agent_id)
        preference_order.sort(key=lambda x: x[1], reverse=True)
        agent = get_agent(str(agent_id), self.db)
        
        json_helper = JsonHelper()
        
        for agent_model in preference_order:
            try:
                model = agent_model[0]
                
                ai_provider = get_provider(db=self.db, identificator=str(model.ai_provider.id))
                      
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
                
                print(1)
                print(model.id)
                print(model.display_name)
                # uapkcuam : UserApiKeyCanUseIaModel = get_user_api_key_can_use_ia_model(db=self.db, identificator=str(model.id), token=self.user_token)
                filter = dict(id_ai_model=model.id)
                list_uapkcuam : list[UserApiKeyCanUseIaModel] = list_user_api_key_can_use_ia_model(db=self.db, filters=filter, token=self.user_token)
                for uapkcuam in list_uapkcuam:
                    print(2)
                    print(uapkcuam.id_user_api_key)
                    print(type(uapkcuam.id_user_api_key))
                                    
                    api_key : UserApiKey = get_user_api_key(db=self.db, token=self.user_token, identificator=uapkcuam.id_user_api_key)

                    ai_model = init_chat_model(model.slug, model_provider=ai_provider.slug, temperature=temperature, api_key=decrypt(api_key.encrypted_key))
                    break
                
                match agent.task:
                    case "manipulate_graph":
                        datamodel = ManipulateGraphResponse          ### TODO Continuar a fazer todos os modelos e selecionar modelo da resposta pela task          
                    case "manipulate_node":
                        datamodel = ManipulateNodeResponse                      
                    case "create_study_session":
                        datamodel = CreateStudySessionResponse                 
                    case "evaluate_essay_question":
                        datamodel = EvaluateEssayQuestionResponse
                    case "create_essay_question":
                        datamodel = CreateEssayQuestionResponse
                    case "create_multiple_choice_question":
                        datamodel = CreateMultipleChoiceQuestionResponse
                    case "evaluate_multiple_choice_question":
                        datamodel = EvaluateMultipleChoiceQuestionResponse
                    case "create_feynman":
                        datamodel = CreateFeynmanResponse
                    case "evaluate_feynman":
                        datamodel = EvaluateFeynmanResponse
                    case "recommend_study_resource":
                        datamodel = RecommendStudyResourceResponse
                    case "study_manager":
                        datamodel = StudyManagerResponse
                    case "study_assistent":
                        datamodel = studyAssistentResponse
                model_struc = ai_model.with_structured_output(datamodel, include_raw=True)

                prompt = ChatPromptTemplate.from_messages({
                    ("system", system_prompt),
                    ("human", "{user_prompt}"),
                })
                
                print(1)
                chain = (prompt | model_struc)
                print(2)
                resultado = chain.invoke({"user_prompt": user_prompt})
                print(3)
                raw: dict = resultado["raw"]
                parsed: ManipulateGraphResponse = resultado["parsed"]

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
                        parsed = json_helper._parse_model_response(
                            failed_generation,
                            ManipulateGraphResponse,
                        )

                        print("JSON recuperado com sucesso:")
                        print(parsed.model_dump_json(indent=2))
                        return parsed.model_dump_json(indent=2)

                    except Exception as exepition:
                        try:
                            print("\n===> Tentativa AI\n")
                            #####                    #####  
                            ## Segunda tentativa com AI ##
                            #####                    #####
                            prompt = ChatPromptTemplate.from_messages({
                                ("system", f"Você é o sistema de tratamento de erro da seguinte tarefa: \"{system_prompt}\". Agora concerte: "),
                                ("human", "{user_prompt}"),
                            })
                            
                            print(11)
                            chain2 = (prompt | model_struc)
                            resultado2 = chain2.invoke({"user_prompt": failed_generation})
                            print(22)
                            raw2: dict = resultado2["raw"]
                            parsed2: ManipulateGraphResponse = resultado2["parsed"]
                            user = get_current_user(token=self.user_token, db=self.db)
                               
                            create_ai_usage_log(AiUsageLogCreate(
                                id_agent_model= str(agent_model[2].id),
                                id_user=user.id,
                                usage_details=raw2.response_metadata,
                            ), self.db, self.user_token)
                            print(resultado2)
                            return resultado2
                        except groq.BadRequestError as ebr2:
                            error2 = ebr2.body.get("error", {})
                            print("\n===> exept groq\n")
                            
                            if error2.get("code") == "tool_use_failed":
                                print("\n===> passou if\n")
                                
                                failed_generation2 = error.get("failed_generation")
                                try:
                                    print("\n===> try dps passou\n")
                                    
                                    parsed2 = json_helper._parse_model_response(
                                        failed_generation2,
                                        ManipulateGraphResponse,
                                    )

                                    print("JSON recuperado com sucesso:")
                                    print(parsed2.model_dump_json(indent=2))
                                    return parsed2.model_dump_json(indent=2)

                                except ValueError as exc2:
                                    print("Falha ao recuperar resposta da IA:")
                                    print(exc2)                                                                                    
        raise Exception("Erro na geração")


