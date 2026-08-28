import os
from pydantic import BaseModel
from langchain_openai import ChatOpenAI

def invoke_llm(model: str, messages: list, schema: type[BaseModel] | None = None, temperature: float = 0.0, **kwargs) -> BaseModel | str:
  """Instantiate ChatOpenAI and invoke it, optionally parsing into a Pydantic schema."""
  llm = ChatOpenAI(
    model=model,
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=temperature,
    **kwargs
  )
  if schema:
    llm = llm.with_structured_output(schema)
  return llm.invoke(messages)
