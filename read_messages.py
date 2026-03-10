import sys
import codecs
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
from app.core.supabase_client import get_supabase

db = get_supabase()
res = db.table('messages').select('content, role, metadata').order('created_at', desc=True).limit(10).execute()

for m in res.data:
    print(f"[{m['role']}] {m['content'][:100]}...\nMetadata: {m.get('metadata')}\n")
