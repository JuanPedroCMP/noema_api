from pydantic import ValidationError
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser, PydanticOutputParser
from langchain_core.runnables import RunnableLambda
from ...ai.services import list_agent_models, get_ai_model, get_agent, get_provider
from ....core.db_models.ai_models import AgentModel, AiModel
from ...ai.models import AgentModelFilters
from sqlalchemy.orm import Session
from ..models import AiGraphResponse
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
from .services import JsonHelper 

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

    # TODO Separar modelos que a api key pode utilizar
    
    # TODO Fazer chain
    def call_ai(self, user_prompt: str, agent_id: UUID):     
        preference_order = self._calculate_preference_order(agent_id=agent_id)
        preference_order.sort(key=lambda x: x[1], reverse=True)
        agent = get_agent(str(agent_id), self.db)
        
        json_helper = JsonHelper()
        
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
                        parsed = json_helper._parse_model_response(
                            failed_generation,
                            AiGraphResponse,
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
                                ("system", f"{system_prompt}. Continue a gerar o agrafo a seguir."),
                                ("human", "{user_prompt}"),
                            })
                            
                            print(11)
                            chain2 = (prompt | model_struc)
                            resultado2 = chain2.invoke({"user_prompt": failed_generation})
                            print(22)
                            raw2: dict = resultado2["raw"]
                            parsed2: AiGraphResponse = resultado2["parsed"]
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
                                        AiGraphResponse,
                                    )

                                    print("JSON recuperado com sucesso:")
                                    print(parsed2.model_dump_json(indent=2))
                                    return parsed2.model_dump_json(indent=2)

                                except ValueError as exc2:
                                    print("Falha ao recuperar resposta da IA:")
                                    print(exc2)

                                raise                    
                    continue

                raise
                print(f"err: {e}")
                
                print(type(e))
                print(repr(e))
                print(e.__dict__)
                
                    

