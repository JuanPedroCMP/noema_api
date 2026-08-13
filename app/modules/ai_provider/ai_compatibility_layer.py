from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser, PydanticOutputParser
from ..ai.services import list_agent_models, get_ai_model, get_agent, get_provider
from ...core.db_models.ai_models import AgentModel, AiModel
from ..ai.models import AgentModelFilters
from sqlalchemy.orm import Session
from .models import AiGraphResponse
from uuid import UUID

class AiProvider:
    def __init__(self, db: Session, user_token: str):
        self.db = db
        self.user_token = user_token
        
    # TODO Cálculo da ordem de preferÊncia
    def _calculate_preference_order(self, agent_id: UUID) -> list[tuple[AiModel, float]]:
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
            model : AiModel = get_ai_model(identificator=agent_model.id_ai_model)
                        
            final_score = score_1 * (model.input_token_limit + model.output_token_limit)
            preference = (model, final_score)
            preference_order.append(preference)
        
        return preference_order     

    # TODO Separar modelos que a api key pode utilizar
    
    # TODO Fazer chain
    def call_ai(self, user_prompt: str, agent_id: UUID):     

        preference_order = self._calculate_preference_order(agent_id=agent_id)
        preference_order.sort(key=lambda x: x[1])
        
        for agent_model in preference_order:
            model = agent_model[0]
            
            ai_provider = get_provider(db=self.db, identificator=model.ai_provider)
            
            # agent_model = list_agent_models(db=self.db, filters=AgentModelFilters(id_agent=agent_id, ))
        
            model = init_chat_model(model.slug, model_provider=ai_provider.slug, temperature=0.3, api_key="")

            model_struc = model.with_structured_output(AiGraphResponse)

            prompt = ChatPromptTemplate.from_messages({
                ("system", "você é o motor de geração de geração de dados de um app, identifique o que o usuário deseja aprender e gere os nodes e as relações do grafo"),
                ("human", "{texto}"),
            })

            chain = prompt | model_struc 
            resultado = chain.invoke({"texto": "Me ensine matemática do ensino médio"})
            print(resultado)
            print(type(resultado))


            # chain = prompt | model_struc | parser

            # resultado = chain.invoke({"texto": "Me ensine matemática do ensino médio"})
            # print(resultado)