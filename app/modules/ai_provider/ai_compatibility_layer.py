from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from ..ai.services import list_agent_models, get_ai_model
from ...core.db_models.ai_models import AgentModel, AiModel
from sqlalchemy.orm import Session
from .models import AiGraphResponse

class AiProvider:
    def __init__(self, db: Session, user_token: str):
        self.db = db
        self.user_token = user_token
        
    # TODO Cálculo da ordem de preferÊncia
    def calculate_preference_order(self) -> dict:
        agents_models: list[AgentModel]  = list_agent_models(db=self.db)
        
        preference_order = {}
        
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
            preference_order[agent_model.id] = final_score
        
        return preference_order
        

    # TODO Separar modelos que a api key pode utilizar
    # TODO Fazer chain

model = init_chat_model("mistral-medium-latest", model_provider="mistralai", temperature=0.3, api_key="tTldVogUKAUgC0Hsw6sTDLSPlLIyMiDz", response_format=AiGraphResponse)

prompt = ChatPromptTemplate.from_messages({
    ("system", "você é o motor de geração de geração de dados de um app, identifique o que o usuário deseja aprender e gere os nodes e as relações do grafo, no formato json"),
    ("human", "{texto}"),
})

parser = JsonOutputParser()

chain = prompt | model | parser

resultado = chain.invoke({"texto": "Me ensine matemática do ensino médio"})
print(resultado)