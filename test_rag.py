import sys
import codecs
sys.path.append(".")
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
from app.services.rag import search_knowledge_base, keyword_search_fallback

queries = [
    "ahora decime la tabla de comisiones que utilizamos para pagarle al asesor comercial ?",
    "bien ahora decime las distintas formas que tiene un jefe de tribu para captar asesores comerciales",
    "bien, ahora conoces las formas en que un asesor puede captar a un adherido, confirmame"
]

with open("test_rag.txt", "w", encoding="utf-8") as f:
    for q in queries:
        f.write(f"\n=============================================\n")
        f.write(f"QUERY: '{q}'\n")
        
        # 1. Semantic Search
        res_sem = search_knowledge_base(q, match_threshold=0.0) # threshold 0 para ver todo
        f.write(f"\n--- SEMANTIC SEARCH (Top 3) ---\n")
        for r in res_sem[:3]:
            f.write(f"Sim: {r.get('similarity', 0):.4f} | Doc: {r.get('document_name')} | Pilar: {r.get('metadata', {}).get('pilar_id', 'None')}\n")
            
        # 2. Keyword fallback
        res_key = keyword_search_fallback(q)
        f.write(f"\n--- KEYWORD FALLBACK ---\n")
        f.write(f"Total found: {len(res_key)}\n")
        for r in res_key[:3]:
            f.write(f"Sim: {r.get('similarity', 0):.4f} | Doc: {r.get('document_name')} | Pilar: {r.get('metadata', {}).get('pilar_id', 'None')}\n")
