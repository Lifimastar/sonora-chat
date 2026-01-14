"""
Cliente para Supabase centralizado (Singleton).
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Cliente principal (CerebroSonora)
_main_client: Client | None = None

# Cliente Tu Guia
_tuguia_client: Client | None = None

def get_supabase() -> Client:
    """Retorna el cliente Supabase principal (singleton)."""
    global _main_client
    if _main_client is None:
        _main_client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )
    return _main_client

def get_tuguia_supabase() -> Client:
    """Retorna el cliente Supabase de Tu Guia (singleton)."""
    global _tuguia_client
    if _tuguia_client is None:
        _tuguia_client = create_client(
            os.getenv("TUGUIA_SUPABASE_URL"),
            os.getenv("TUGUIA_SUPABASE_SERVICE_KEY")
        )
    return _tuguia_client