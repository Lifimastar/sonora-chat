"""
Servidor FastAPI para la API de chat.
Se ejecuta separado del bot de voz.
"""
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.api.chat_api import router as chat_router
from app.api.agents_api import router as agents_router

app = FastAPI(title="Bot Sonora Chat API", version="1.0.0")

# CORS para el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("CHAT_API_PORT", 7861))
    print(f"🚀 Chat API running on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)