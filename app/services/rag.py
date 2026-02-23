"""
Servicio RAG para búsqueda semántica en la base de conocimiento.
"""

import os
from typing import List, Dict
from functools import lru_cache
from dotenv import load_dotenv
from openai import OpenAI
#from supabase import create_client, Client
from app.core.supabase_client import get_supabase

load_dotenv()

# Configuración
OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_query_embedding(query: str) -> List[float]:
    """Genera embedding para la consulta del usuario"""
    response = OPENAI_CLIENT.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    return response.data[0].embedding

@lru_cache(maxsize=100)
def generate_query_embedding_cached(query: str) -> tuple:
    """
    Version cacheada de generate_query_embedding.
    Retorna tuple para ser hashable (requerido por lru_cache).
    """
    embedding = generate_query_embedding(query)
    return tuple(embedding)

def search_knowledge_base(
    query: str, 
    match_threshold: float = 0.35,
    match_count: int = 3
) -> List[Dict]:
    """
    Busca en la base de conocimiento usando similitud semántica.
    
    Args:
        query: Pregunta del usuario
        match_threshold: Umbral mínimo de similitud (0-1)
        match_count: Número máximo de resultados
    
    Returns:
        Lista de chunks relevantes con metadata
    """
    supabase = get_supabase()
    query_embedding = list(generate_query_embedding_cached(query))
    
    # Buscar en Supabase usando la función match_documents
    response = supabase.rpc(
        'match_documents',
        {
            'query_embedding': query_embedding,
            'match_threshold': match_threshold,
            'match_count': match_count
        }
    ).execute()
    
    return response.data

def format_context_for_llm(search_results: List[Dict]) -> str:
    """
    Formatea los resultados de búsqueda para el LLM.
    
    Args:
        search_results: Resultados de la búsqueda
    
    Returns:
        Contexto formateado como string
    """
    if not search_results:
        return "No se encontró información relevante en la base de conocimiento."
    
    context_parts = []
    
    for idx, result in enumerate(search_results, 1):
        doc_name = result.get('document_name', 'Documento desconocido')
        chunk_text = result.get('chunk_text', '')
        similarity = result.get('similarity', 0)
        metadata = result.get('metadata') or {}
        
        # Header claro y prominente con nombre del documento
        part = f"═══ DOCUMENTO: {doc_name} (relevancia: {similarity:.0%}) ═══\n"
        
        # Agregar resumen si existe
        summary = metadata.get('summary', '')
        if summary and summary != "Sin resumen":
            part += f"Resumen: {summary}\n"
        
        part += f"\n{chunk_text}"
        context_parts.append(part)
    
    context = "\n\n---\n\n".join(context_parts)
    context += "\n\n⚠️ RECUERDA: cita EXACTAMENTE el nombre del DOCUMENTO de donde sacaste la información. Solo usa lo que está arriba, NO inventes."
    return context

def keyword_search_fallback(query: str, max_results: int = 3) -> List[Dict]:
    """
    Búsqueda por palabras clave como fallback cuando la búsqueda semántica falla.
    Busca en chunk_text y document_name usando ILIKE.
    """
    import re
    supabase = get_supabase()
    
    # Extraer palabras significativas (>= 3 chars, sin stopwords)
    stopwords = {'que', 'del', 'los', 'las', 'una', 'uno', 'con', 'por', 'para', 'como', 
                 'más', 'esta', 'este', 'ese', 'eso', 'son', 'tiene', 'dice', 'hay',
                 'qué', 'cómo', 'cuál', 'dónde', 'quién', 'archivo', 'documento'}
    words = re.findall(r'\w+', query.lower())
    keywords = [w for w in words if len(w) >= 3 and w not in stopwords]
    
    if not keywords:
        return []
    
    results = []
    
    # 1. Buscar por nombre de documento (si el query contiene algo que parezca un filename)
    for kw in keywords:
        response = supabase.from_('knowledge_base') \
            .select('id, document_name, document_type, chunk_text, metadata') \
            .ilike('document_name', f'%{kw}%') \
            .limit(max_results) \
            .execute()
        if response.data:
            for r in response.data:
                r['similarity'] = 0.5  # Score artificial para fallback
            results.extend(response.data)
            break
    
    # 2. Si no encontramos por nombre, buscar en chunk_text
    if not results:
        for kw in keywords:
            response = supabase.from_('knowledge_base') \
                .select('id, document_name, document_type, chunk_text, metadata') \
                .ilike('chunk_text', f'%{kw}%') \
                .limit(max_results) \
                .execute()
            if response.data:
                for r in response.data:
                    r['similarity'] = 0.4  # Score más bajo para match por texto
                results.extend(response.data)
                break
    
    # Deduplicar por id
    seen = set()
    unique = []
    for r in results:
        if r['id'] not in seen:
            seen.add(r['id'])
            unique.append(r)
    
    return unique[:max_results]

def get_relevant_context(query: str) -> str:
    """
    Función principal para obtener contexto relevante.
    Usa búsqueda semántica + fallback por keywords.
    """
    # 1. Búsqueda semántica (principal)
    results = search_knowledge_base(query, match_threshold=0.35, match_count=5)
    
    # Log para debug
    if results:
        sims = [f"{r.get('similarity',0):.3f}" for r in results]
        print(f"🔍 RAG: query='{query[:50]}' → {len(results)} resultados, sims=[{', '.join(sims)}]")
    else:
        print(f"🔍 RAG: query='{query[:50]}' → SIN RESULTADOS semánticos")
        
        # 2. Fallback: búsqueda por keywords
        results = keyword_search_fallback(query)
        if results:
            print(f"🔍 RAG FALLBACK: encontrados {len(results)} resultados por keywords")
        else:
            print(f"🔍 RAG FALLBACK: tampoco encontró resultados por keywords")
    
    # Formatear para el LLM
    context = format_context_for_llm(results)
    
    return context
# Función de prueba
if __name__ == "__main__":
    # Prueba el servicio RAG
    test_query = "¿Cuáles son las obligaciones de un adherido?"
    
    print(f"🔍 Buscando: {test_query}\n")
    context = get_relevant_context(test_query)
    print("📄 Contexto encontrado:")
    print(context)