"""FastAPI application for the ENT Surveillance dashboard."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

app = FastAPI(
  title="ENT Surveillance API",
  description="Backend API for the ENT Monitor dashboard",
  version="0.1.0",
)

# Allow the Next.js dev server and common local origins
app.add_middleware(
  CORSMiddleware,
  allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
  ],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health_check():
  return {"status": "ok"}
