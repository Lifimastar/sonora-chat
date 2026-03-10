import os
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from openai import OpenAI
from loguru import logger
from app.services.database import DatabaseService

router = APIRouter()

# Cliente de OpenAI para usar la Assistants API
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=60.0, # Más tiempo por si suben archivos grandes
    default_headers={"OpenAI-Beta": "assistants=v2"}
)

@router.post("")
async def create_agent(
    name: str = Form(...),
    description: Optional[str] = Form(""),
    system_prompt: str = Form(...),
    files: List[UploadFile] = File(None)
):
    """Crea un asistente en OpenAI y guarda su referencia en Supabase."""
    try:
        logger.info(f"🤖 Creando Agente Especializado: {name}")
        
        vector_store_id = None
        file_ids = []

        # 1. Si hay archivos, subirlos a OpenAI y crear un Vector Store
        if files and len(files) > 0 and files[0].filename != "":
            logger.info(f"📂 Archivos recibidos para el agente: {len(files)}")
            vector_stores = getattr(client.beta, "vector_stores", getattr(client, "vector_stores", None))
            vector_store = vector_stores.create(name=f"KB_{name}")
            vector_store_id = vector_store.id
            
            # Subir archivos y asociarlos al vector store
            file_streams = []
            for file in files:
                contents = await file.read()
                # Tupla (filename, file_content, content_type) requerida por OpenAI
                file_streams.append((file.filename, contents))
                
            logger.info("Subiendo archivos a OpenAI (Vector Store)...")
            file_batch = vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id,
                files=file_streams
            )
            logger.info(f"✅ Archivos subidos. Estado: {file_batch.status}")

        # 2. Configurar el Assistant
        tools = []
        tool_resources = {}
        
        if vector_store_id:
            tools.append({"type": "file_search"})
            tool_resources = {"file_search": {"vector_store_ids": [vector_store_id]}}

        # 3. Crear el Assistant en OpenAI
        assistants = getattr(client.beta, "assistants", getattr(client, "assistants", None))
        assistant = assistants.create(
            name=name,
            instructions=system_prompt,
            model="gpt-4o-mini",
            tools=tools,
            tool_resources=tool_resources if tool_resources else None
        )
        
        logger.info(f"🧠 Assistant creado en OpenAI: {assistant.id}")

        # 4. Guardar en Supabase
        db_service = DatabaseService()
        data = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "assistant_id": assistant.id
        }
        
        # En una API real sacaríamos el usuario autenticado del token
        # Asumiremos admin por defecto para la creación interna
        
        response = db_service.client.table("custom_agents").insert(data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Error guardando en Supabase")
            
        logger.info(f"✅ Agente registrado en Supabase exitosamente: {response.data[0]['id']}")
        
        return {
            "success": True, 
            "agent": response.data[0]
        }
        
    except Exception as e:
        logger.error(f"❌ Error al crear agente: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def list_agents():
    """Lista todos los agentes especializados disponibles."""
    try:
        db_service = DatabaseService()
        response = db_service.client.table("custom_agents").select("*").order("created_at", desc=True).execute()
        return {"success": True, "agents": response.data}
    except Exception as e:
        logger.error(f"❌ Error listando agentes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Borra un agente de la DB local y de OpenAI"""
    try:
        db_service = DatabaseService()
        
        # Obtener ID de OpenAI antes de borrar de DB
        resp = db_service.client.table("custom_agents").select("assistant_id").eq("id", agent_id).execute()
        
        if not resp.data:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
            
        assistant_id = resp.data[0]["assistant_id"]
        
        # Borrar de OpenAI
        try:
            assistants = getattr(client.beta, "assistants", getattr(client, "assistants", None))
            assistants.delete(assistant_id)
            logger.info(f"🗑️ Assistant {assistant_id} eliminado de OpenAI")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo eliminar de OpenAI (tal vez ya no existía): {e}")
            
        # Borrar de Supabase
        db_service.client.table("custom_agents").delete().eq("id", agent_id).execute()
        
        return {"success": True, "message": "Agente eliminado"}
        
    except Exception as e:
        logger.error(f"❌ Error eliminando agente: {e}")
        raise HTTPException(status_code=500, detail=str(e))
