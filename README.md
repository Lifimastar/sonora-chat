# Sonora Chat API

> API de chat de texto para el Ecosistema Sonora - Desplegado en Coolify

## 🌐 Ecosistema Sonora

| Repo | Descripción | Deploy |
|------|-------------|--------|
| [sonora-frontend](https://github.com/Lifimastar/sonora-frontend) | UI Next.js | Coolify |
| [sonora-test](https://github.com/Lifimastar/sonora-test) | Bot de voz Pipecat | Pipecat Cloud |
| **sonora-chat** (este) | API de chat texto | Coolify |

---

## 🚀 Desarrollo Local

```bash
# Activar PYTHONPATH
$env:PYTHONPATH = "."  # PowerShell
# export PYTHONPATH="."  # Bash

# Correr servidor
uv run python -m app.api.server
# Escucha en http://localhost:7861
```

---

## 📁 Estructura

```
sonora-chat/
├── app/
│   └── api/
│       ├── server.py       # FastAPI server
│       └── routes/
│           └── chat.py     # Endpoint /api/chat
├── pyproject.toml          # Dependencias
└── .env                    # Variables de entorno
```

---

## ⚙️ Variables de Entorno

```env
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
OPENAI_API_KEY=...
CHAT_API_PORT=7861
```

---

## 🔌 Endpoints

### POST /api/chat

Recibe mensajes de texto y/o imágenes, retorna respuesta del bot.

```json
{
  "message": "Hola",
  "conversation_id": "uuid",
  "user_id": "uuid",
  "image_urls": ["https://..."]
}
```

### GET /health

Health check para Coolify.

---

## 🔄 Deploy

Push a `main` → Coolify despliega automáticamente

```bash
git add .
git commit -m "feat: descripción"
git push origin main
```
