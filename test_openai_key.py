"""Probador rapido de OPENAI_API_KEY.

Verifica que la key sirva para las 3 APIs que usa sonora-chat:
  1. Auth basica (GET /v1/models)
  2. Chat completion (gpt-4o-mini)
  3. Embeddings (text-embedding-3-small)

Uso:
  # Con variable de entorno
  uv run python test_openai_key.py

  # Con archivo .env (se carga automaticamente si existe)
  uv run python test_openai_key.py

  # Con key explicita (no recomendado, queda en historial de shell)
  uv run python test_openai_key.py sk-proj-XXXX
"""

import os
import sys
from pathlib import Path

try:
    from openai import OpenAI, AuthenticationError, APIError
except ImportError:
    print("[X] Falta la libreria 'openai'. Instalar con: uv add openai")
    sys.exit(2)


def cargar_env():
    """Carga .env del directorio actual sin requerir python-dotenv."""
    env = Path(__file__).parent / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(clave, valor)


def obtener_key() -> str:
    if len(sys.argv) > 1 and sys.argv[1].startswith("sk-"):
        return sys.argv[1]
    cargar_env()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        print("[X] No se encontro OPENAI_API_KEY (ni en argv ni en env ni en .env)")
        sys.exit(2)
    return key


def enmascarar(key: str) -> str:
    if len(key) < 12:
        return "***"
    return f"{key[:10]}...{key[-4:]}"


def main() -> int:
    key = obtener_key()
    print(f"\n[*] Probando key: {enmascarar(key)}")
    print(f"[*] Longitud: {len(key)} caracteres")
    print("=" * 60)

    client = OpenAI(api_key=key)
    fallos = 0

    # 1. Auth basica - listar models
    print("\n[1/3] Auth basica (GET /v1/models)...")
    try:
        models = client.models.list()
        count = sum(1 for _ in models)
        print(f"    [OK] Key valida. {count} modelos disponibles.")
    except AuthenticationError as e:
        print(f"    [X] 401 Unauthorized: {e}")
        print("    -> La key esta revocada, mal copiada o del workspace equivocado.")
        return 1
    except APIError as e:
        print(f"    [X] Error API: {e}")
        fallos += 1

    # 2. Chat completion - lo que usa el endpoint /api/chat
    print("\n[2/3] Chat completion (gpt-4o-mini)...")
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Responde solo con la palabra OK"}],
            max_tokens=10,
        )
        contenido = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        print(f"    [OK] Respuesta: {contenido.strip()!r} ({tokens} tokens)")
    except Exception as e:
        print(f"    [X] Fallo: {type(e).__name__}: {e}")
        if "insufficient_quota" in str(e) or "billing" in str(e).lower():
            print("    -> Sin saldo o limite alcanzado. Ver platform.openai.com/billing")
        fallos += 1

    # 3. Embeddings - lo que usa el RAG
    print("\n[3/3] Embeddings (text-embedding-3-small)...")
    try:
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input="prueba de embedding",
        )
        dim = len(resp.data[0].embedding)
        print(f"    [OK] Embedding generado ({dim} dimensiones)")
    except Exception as e:
        print(f"    [X] Fallo: {type(e).__name__}: {e}")
        fallos += 1

    print("\n" + "=" * 60)
    if fallos == 0:
        print("[OK] Todo verde. La key sirve para sonora-chat.")
        return 0
    print(f"[X] {fallos} prueba(s) fallaron. Revisar arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
