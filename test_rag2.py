import sys
import codecs
import os
from dotenv import load_dotenv
load_dotenv()

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
sys.path.append(".")
from app.services.rag import search_knowledge_base

queries = [
    "tabla de comisiones asesor comercial",
    "formas captar asesores comerciales jefe tribu",
    "formas asesor capta adherido"
]

with open("test_rag2.txt", "w", encoding="utf-8") as f:
    for q in queries:
        f.write(f"\n=============================================\n")
        f.write(f"QUERY: '{q}'\n")
        res_sem = search_knowledge_base(q, match_threshold=0.0)
        f.write(f"\n--- SEMANTIC SEARCH (Top 3) ---\n")
        for r in res_sem[:3]:
            f.write(f"Sim: {r.get('similarity', 0):.4f} | Doc: {r.get('document_name')}\n")
