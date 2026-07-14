import asyncio
from layers.ingestion.orchestrator import run_ingestion


def main():
  asyncio.run(run_ingestion())


if __name__ == "__main__":
  main()
