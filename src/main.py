from fastapi import FastAPI
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_call_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from config import Config
from skills import search_knowledge_base
from harness import Harness

app = FastAPI(title="Learn AI App", version="1.0.0")


class QueryRequest(BaseModel):
    question: str
    
    
class QueryResponse(BaseModel):
    code: int
    data: str
    cost_ms: int
    
    
def build_agent():
    llm = ChatOpenAI(
        model_name=Config.OPENAI_MODEL_NAME,
        api_key=Config.OPENAI_API_KEY,
        base_url=Config.OPENAI_API_BASE_URL,
        temperature=0.1,
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的问答助手，请优先使用检索工具获取事实依据，回答要简洁准确。"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}")
    ])
    
    agent = create_tool_call_agent(
        llm=llm,
        tools=[search_knowledge_base],
        prompt=prompt,
        verbose=True,
    )
    
    agent_executor = AgentExecutor(
        agent=agent,
        tools=[search_knowledge_base],
        verbose=True,
    )
    
    return agent_executor


agent_executor = build_agent()
harness = Harness(executor=lambda question: agent_executor.invoke({"input": question})["output"])


@app.post("/chat", response_model=QueryResponse)
def chat(request: QueryRequest):
    result = harness.run(request.question)
    return QueryResponse(**result)
    