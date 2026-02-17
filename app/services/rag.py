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
    match_threshold: float = 0.78,
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

def get_relevant_context(query: str) -> str:
    """
    Función principal para obtener contexto relevante.
    """
    # Buscar documentos relevantes
    # Umbral 0.55 para evitar chunks irrelevantes que causan alucinaciones
    results = search_knowledge_base(query, match_threshold=0.55, match_count=4)
    
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