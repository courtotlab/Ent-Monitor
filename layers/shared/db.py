import os
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
  url = os.getenv("DATABASE_URL")
  if not url:
    raise ValueError("DATABASE_URL environment variable is required")
  return url


@contextmanager
def get_connection():
  conn = psycopg2.connect(get_database_url())
  try:
    yield conn
    conn.commit()
  except Exception:
    conn.rollback()
    raise
  finally:
    conn.close()
