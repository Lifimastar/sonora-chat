from app.core.supabase_client import get_supabase

res = get_supabase().table('pilares').select('id, nombre, system_prompt').execute()
with open('pilares_out.txt', 'w', encoding='utf-8') as f:
    for p in res.data:
        f.write(f"\nPILAR {p['id']} - {p['nombre']}:\n{p['system_prompt']}\n")
        f.write("-" * 50 + "\n")
