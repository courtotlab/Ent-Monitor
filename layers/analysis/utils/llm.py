import os
from typing import Any
from langchain_openai import ChatOpenAI

def invoke_llm(model: str, messages: list, schema: Any = None, temperature: float = 0.0, **kwargs) -> Any:
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
