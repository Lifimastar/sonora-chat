import sys
import codecs
sys.path.append(".")
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
from app.core.supabase_client import get_supabase

res = get_supabase().table("pilares").select("id, nombre, system_prompt").execute()
for p in res.data:
    print(f"[{p['id']}] {p['nombre']}:\n{p['system_prompt']}\n{'-'*50}")
