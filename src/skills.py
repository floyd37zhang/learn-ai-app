from langchain_core.tools import tool
from retriever import get_retriever
from config import Config


@tool
def search_knowledge_base(query: str) -> str:
    retriever = get_retriever(Config.CHROMA_DB_PATH)
    docs = retriever.invoke(query)
    if not docs:
        return "没有找到相关文档"
    
    return "\n\n".join([doc.page_content for doc in docs])
    
