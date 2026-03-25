"""
API HTTP para chat de texto.
Usa la misma lógica del bot de voz (OpenAI + Tools).
"""
import os
import json
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
from loguru import logger

from app.services.database import DatabaseService
from app.services.rag import get_relevant_context
from app.services.tuguia_database import TuGuiaDatabase
from app.prompts import SYSTEM_PROMPT, get_system_prompt

router = APIRouter()

# Cliente OpenAI configurado para Assistants V2
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=30.0,
    default_headers={"OpenAI-Beta": "assistants=v2"}
)

class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    user_id: Optional[str] = None
    camera_image: Optional[str] = None  # Imagen base64 de la cámara
    pilar_id: Optional[int] = None  # ID del pilar del usuario
    agent_id: Optional[str] = None  # ID de OpenAI Assistant (si eligió un agente especializado)

# Definir las tools para el LLM (mismas que en bot.py)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_informacion",
            "description": "¡OBLIGATORIO usar esta tool antes de responder preguntas sobre la empresa, comisiones, operaciones, manuales o pilares! Busca información oficial en la base de conocimiento (PDFs, CVs, reglamentos, contratos).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La consulta a buscar"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "contar_usuarios_tuguia",
            "description": "Cuenta el total de usuarios registrados en Tu Guía Argentina.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "contar_usuarios_por_subcategoria",
            "description": "Cuenta usuarios por subcategorías específicas en Tu Guía.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subcategory_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de nombres de subcategorías"
                    }
                },
                "required": ["subcategory_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "guardar_dato",
            "description": "Guarda un dato, preferencia o gusto del usuario en la memoria persistente. ¡NO usar para buscar ni registrar procesos operativos de la empresa!",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nombre del dato"},
                    "value": {"type": "string", "description": "Valor a guardar"},
                    "scope": {"type": "string", "enum": ["user", "public"], "description": "user=personal, public=compartido"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "borrar_dato",
            "description": "Borra un dato de la memoria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nombre del dato a borrar"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ver_camara",
            "description": "Captura y analiza lo que ve la cámara del usuario. Úsala cuando te pregunten qué ves, qué tienes enfrente, o cualquier pregunta visual.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_actividad",
            "description": "Consulta estadísticas de actividad del ecosistema: cantidad de conversaciones, mensajes, usuarios activos, documentos en knowledge base, y actividad por período. Úsala cuando pregunten por reportes, estadísticas, actividad, o cuántas conversaciones/mensajes hay.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["resumen_general", "actividad_hoy", "actividad_semana", "actividad_mes"],
                        "description": "Tipo de consulta: resumen_general=totales globales, actividad_hoy=actividad del dia, actividad_semana=ultimos 7 dias, actividad_mes=ultimos 30 dias"
                    }
                },
                "required": ["tipo"]
            }
        }
    }
]

def execute_tool(tool_name: str, arguments: dict, db_service: DatabaseService, user_id: str = None, pilar_id: int = None) -> dict:
    """Ejecuta una tool y retorna el resultado."""
    try:
        if tool_name == "buscar_informacion":
            query = arguments.get("query", "")
            context = get_relevant_context(query, pilar_id=pilar_id)
            return {"success": True, "informacion": context}
        
        elif tool_name == "contar_usuarios_tuguia":
            tuguia_db = TuGuiaDatabase()
            count = tuguia_db.count_users()
            return {"success": True, "total_usuarios": count, "mensaje": f"Hay {count} usuarios registrados."}
        
        elif tool_name == "contar_usuarios_por_subcategoria":
            subcategory_names = arguments.get("subcategory_names", [])
            tuguia_db = TuGuiaDatabase()
            result = tuguia_db.count_users_by_subcategory(subcategory_names)
            return result
        
        elif tool_name == "guardar_dato":
            key = arguments.get("key")
            value = arguments.get("value")
            scope = arguments.get("scope", "user")
            target_user_id = user_id if scope == "user" else None
            success = db_service.save_memory(key, value, user_id=target_user_id)
            return {"success": success, "mensaje": f"Dato '{key}' guardado."}
        
        elif tool_name == "borrar_dato":
            key = arguments.get("key")
            success = db_service.delete_memory(key, user_id=user_id)
            return {"success": success, "mensaje": f"Dato '{key}' borrado."}
        
        elif tool_name == "ver_camara":
            # Se maneja de forma especial en el endpoint
            return {"success": True, "use_camera": True}
        
        elif tool_name == "consultar_actividad":
            tipo = arguments.get("tipo", "resumen_general")
            result = db_service.get_activity_stats(tipo)
            return result
        
        else:
            return {"success": False, "error": f"Tool '{tool_name}' no implementada"}
    
    except Exception as e:
        logger.error(f"Error ejecutando tool {tool_name}: {e}")
        return {"success": False, "error": str(e)}

def get_conversation_history(conversation_id: str, db_service: DatabaseService) -> list:
    """Obtiene historial formateado para OpenAI."""
    history = db_service.get_conversation_history(conversation_id)
    # Convertir 'agent' a 'assistant' para OpenAI
    for msg in history:
        if msg["role"] == "agent":
            msg["role"] = "assistant"
    return history

def get_user_memory(user_id: str, db_service: DatabaseService) -> str:
    """Obtiene memoria del usuario como texto."""
    memories = db_service.get_all_memories(user_id)
    if not memories:
        return ""
    # memories es un diccionario {key: value}, iteramos sobre items()
    memory_text = "\n".join([f"- {key}: {value}" for key, value in memories.items()])
def get_or_create_thread(conversation_id: str, db_service: DatabaseService) -> str:
    """Consulteer o crear un Thread de OpenAI asociado a una conversación específica."""
    response = db_service.client.table("conversations").select("metadata").eq("id", conversation_id).execute()
    if not response.data:
        return None
        
    metadata = response.data[0].get("metadata", {})
    if "openai_thread_id" in metadata:
        return metadata["openai_thread_id"]
        
    # Crear nuevo thread
    thread = client.beta.threads.create()
    metadata["openai_thread_id"] = thread.id
    
    # Guardar en DB
    db_service.client.table("conversations").update({"metadata": metadata}).eq("id", conversation_id).execute()
    logger.info(f"🧵 Nuevo Thread creado en OpenAI: {thread.id}")
    return thread.id

@router.post("/chat")
async def chat(request: ChatRequest):
    """Endpoint principal de chat."""
    logger.info(f"📥 Payload recibido en FastAPI /chat: agent_id={request.agent_id}, pilar={request.pilar_id}, message={request.message[:20]}...")
    
    db_service = DatabaseService()
    db_service.conversation_id = request.conversation_id
    db_service.user_id = request.user_id
    
    try:
        # 1. Guardar mensaje del usuario
        db_service.add_message("user", request.message)
        
        # --- FLUJO DE AGENTE ESPECIALIZADO (OpenAI Assistants) ---
        if request.agent_id:
            logger.info(f"🦸‍♂️ Usando Agente Especializado: {request.agent_id}")
            thread_id = get_or_create_thread(request.conversation_id, db_service)
            
            if not thread_id:
                raise HTTPException(status_code=404, detail="No se encontró la conversación.")
            
            # 1. Añadir el mensaje al hilo
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=request.message
            )
            
            # 2. Correr el Assistant con stream
            # Forzamos las instrucciones para que la IA priorice la búsqueda en sus archivos
            stream = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=request.agent_id,
                instructions="PRIORIDAD ABSOLUTA: Utiliza la herramienta 'file_search' para buscar en tu base de conocimiento OBLIGATORIAMENTE antes de responder si el usuario pregunta algo relacionado con tu dominio de especialidad o con los archivos que tienes adjuntos.",
                stream=True
            )
            
            async def generate_assistant():
                full_response = ""
                try:
                    for event in stream:
                        # Extraer deltas de mensaje
                        if event.event == "thread.message.delta":
                            content_delta = event.data.delta.content[0]
                            if content_delta.type == 'text':
                                text_val = content_delta.text.value
                                full_response += text_val
                                yield f"data: {json.dumps({'content': text_val})}\n\n"
                    
                    # Una vez terminado el stream, guardar en DB
                    db_service.add_message("agent", full_response)
                    yield "data: [DONE]\n\n"
                    
                except Exception as e:
                    logger.error(f"Error en streaming de assistant: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    
            return StreamingResponse(generate_assistant(), media_type="text/event-stream")

        # --- FLUJO NORMAL (Sonora General - Chat Completions) ---
        # 2. Obtener contexto
        history = get_conversation_history(request.conversation_id, db_service)
        memory = get_user_memory(request.user_id, db_service) if request.user_id else ""
        
        # 3. Construir mensajes (prompt dinámico por pilar)
        base_prompt = get_system_prompt(request.pilar_id)
        system_content = base_prompt + """

NOTA: Estás respondiendo en modo TEXTO (no voz). Sigue las reglas de FORMATO MARKDOWN del prompt."""
        
        if memory:
            system_content += memory
        
        messages = [
            {"role": "system", "content": system_content},
            *history,
            {"role": "user", "content": request.message}
        ]
        
        # 4. Llamar a OpenAI con tools
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            stream=False  # Primero sin stream para manejar tools
        )
        
        assistant_message = response.choices[0].message
        
        # 5. Si hay tool calls, ejecutarlas
        if assistant_message.tool_calls:
            # Agregar mensaje del asistente con tool calls
            messages.append(assistant_message.model_dump())
            
            use_camera_model = False  # Flag para usar el modelo con visión
            
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                logger.info(f"🔧 Ejecutando tool: {tool_name}")
                
                # Manejo especial de ver_camara
                if tool_name == "ver_camara":
                    if request.camera_image:
                        logger.info("📷 Inyectando imagen de cámara al contexto")
                        # Agregar resultado exitoso
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"success": True, "mensaje": "Imagen capturada. Analízala y describe lo que ves."})
                        })
                        # Agregar la imagen como mensaje de usuario
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Esta es la imagen de mi cámara. Descríbela detalladamente."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{request.camera_image}"}}
                            ]
                        })
                        use_camera_model = True
                    else:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"success": False, "mensaje": "No hay imagen de cámara disponible. Asegúrate de que tu cámara esté encendida."})
                        })
                else:
                    result = execute_tool(tool_name, arguments, db_service, request.user_id, request.pilar_id)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
            
            # Segunda llamada para obtener respuesta final
            # Usar gpt-4o si hay imagen, sino gpt-4o-mini
            model = "gpt-4o" if use_camera_model else "gpt-4o-mini"
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True
            )
        else:
            # Sin tools, hacer streaming directamente
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True
            )
        
        # 6. Streaming de respuesta
        async def generate():
            full_response = ""
            try:
                # Ejecutar el iterador síncrono en un thread para no bloquear el event loop
                loop = asyncio.get_event_loop()
                queue: asyncio.Queue = asyncio.Queue()

                def _stream_to_queue():
                    try:
                        for chunk in response:
                            content = chunk.choices[0].delta.content
                            if content:
                                loop.call_soon_threadsafe(queue.put_nowait, content)
                        loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel
                    except Exception as e:
                        loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))

                import threading
                thread = threading.Thread(target=_stream_to_queue, daemon=True)
                thread.start()

                while True:
                    item = await queue.get()
                    if item is None:  # sentinel = done
                        break
                    if isinstance(item, Exception):
                        raise item
                    full_response += item
                    yield f"data: {json.dumps({'content': item})}\n\n"
                    await asyncio.sleep(0)  # yield control so chunk gets sent

                db_service.add_message("agent", full_response)
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Error en streaming: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream",
                                  headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
    
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_file(
    files: List[UploadFile] = File(...), # Ahora aceptamos lista
    conversation_id: str = Form(...),
    user_id: str = Form(None),
    message: str = Form(""),
    image_urls: str = Form(""),  # URLs de imágenes externas (si las hay)
    pilar_id: int = Form(None),  # ID del pilar del usuario
    agent_id: str = Form(None)   # ID del asistente especializado si aplica
):
    """Endpoint para subir múltiples archivos con mensaje opcional."""
    db_service = DatabaseService()
    db_service.conversation_id = conversation_id
    db_service.user_id = user_id

    try:
        combined_text_content = ""
        processed_files_names = []
        # Importar dependencias dentro de la función para asegurar que estan disponibles
        import base64
        import io
        
        # Lista de mensajes de contenido multimodal para OpenAI
        openai_content = [{"type": "text", "text": message if message.strip() else "Analiza los archivos adjuntos."}]
        
        # Procesar imágenes externas primero (si las hay)
        if image_urls:
            urls = [url.strip() for url in image_urls.split(",") if url.strip()]
            for url in urls:
                openai_content.append({"type": "image_url", "image_url": {"url": url}})

        for file in files:
            # Leer archivo
            file_content = await file.read()
            MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB
            
            if len(file_content) > MAX_FILE_SIZE:
                 logger.warning(f"Archivo {file.filename} ignorado por tamaño excesivo")
                 continue

            file_name = file.filename
            file_type = file.content_type
            processed_files_names.append(file_name)
            
            logger.info(f"📁 Archivo recibido: {file_name} (MIME: {file_type})")

            # 1. IMAGENES
            if file_type and file_type.startswith("image/"):
                image_base64 = base64.b64encode(file_content).decode("utf-8")
                openai_content.append({
                    "type": "image_url", 
                    "image_url": {"url": f"data:{file_type};base64,{image_base64}"}
                })
            
            # 2. PDF
            elif file_type == "application/pdf" or (file_name and file_name.lower().endswith(".pdf")):
                from pypdf import PdfReader
                try:
                    pdf_reader = PdfReader(io.BytesIO(file_content))
                    pdf_text = f"\n\n--- Contenido PDF: {file_name} ---\n"
                    for page in pdf_reader.pages:
                         pdf_text += page.extract_text() + "\n"
                    combined_text_content += pdf_text
                except Exception as e:
                    logger.error(f"Error PDF {file_name}: {e}")
                    combined_text_content += f"\n[Error leyendo PDF {file_name}]"

            # 3. DOCX
            elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or (file_name and file_name.lower().endswith(".docx")):
                from docx import Document
                try:
                    doc = Document(io.BytesIO(file_content))
                    docx_text = f"\n\n--- Contenido DOCX: {file_name} ---\n"
                    docx_text += "\n".join([para.text for para in doc.paragraphs])
                    combined_text_content += docx_text
                except Exception as e:
                    logger.error(f"Error DOCX {file_name}: {e}")
                    combined_text_content += f"\n[Error leyendo DOCX {file_name}]"

            # 4. TEXTO PLANO
            elif file_type in ["text/plain", "text/markdown"] or (file_name and file_name.lower().endswith((".txt", ".md", ".json"))):
                 text = file_content.decode("utf-8")
                 combined_text_content += f"\n\n--- Contenido {file_name} ---\n{text}"
            
            else:
                 combined_text_content += f"\n[Archivo adjunto no legible: {file_name}]"

        # Guardar en DB
        # Construimos el mensaje del usuario con referencias a TODOS los archivos
        files_str = ", ".join([f"[{name}]" for name in processed_files_names])
        
        # Mofidicación CRÍTICA: Guardar el contenido del texto en el historial para persistencia
        user_msg = f"{message}\n📄 Adjuntos: {files_str}"
        if combined_text_content:
            # Añadimos el contenido de los archivos al mensaje guardado para que quede en memoria
            user_msg += f"\n\n[CONTENIDO DE ARCHIVOS]:\n{combined_text_content[:30000]}" # Limitamos a ~30k caracteres para no saturar DB
        
        # Si hubo URLs de imágenes externas, las pasamos también
        img_list_db = [url.strip() for url in image_urls.split(",") if url.strip()] if image_urls else []
        db_service.add_message("user", user_msg, images=img_list_db)

        # Agregar texto extraído al contexto de OpenAI (si ya lo metimos en user_msg, no hace falta duplicarlo aqui si usamos el historial, PERO
        # en este turno especifico 'openai_content' se usa directo.
        # Sin embargo, como 'openai_content' es una lista multimodal, el texto base ya incluye "Analiza los archivos...".
        # Podemos añadir el contenido extraido tambien para asegurarnos que lo lea con prioridad.
        if combined_text_content:
             openai_content.append({"type": "text", "text": f"\n\nCONTENIDO EXTRAÍDO:\n{combined_text_content[:30000]}"})

        # --- FLUJO DE AGENTE ESPECIALIZADO (OpenAI Assistants) ---
        if agent_id:
            logger.info(f"🦸‍♂️ Subida de archivo para Agente Especializado: {agent_id}")
            thread_id = get_or_create_thread(conversation_id, db_service)
            
            if not thread_id:
                raise HTTPException(status_code=404, detail="No se encontró la conversación.")
            
            # 1. Añadir el mensaje multimodal al hilo
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=openai_content
            )
            
            # 2. Correr el Assistant con stream
            stream = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=agent_id,
                stream=True
            )
            
            async def generate_assistant():
                full_response = ""
                try:
                    for event in stream:
                        if event.event == "thread.message.delta":
                            content_delta = event.data.delta.content[0]
                            if content_delta.type == 'text':
                                text_val = content_delta.text.value
                                full_response += text_val
                                yield f"data: {json.dumps({'content': text_val})}\n\n"
                    
                    db_service.add_message("agent", full_response)
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    logger.error(f"Error en streaming de assistant upload: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    
            return StreamingResponse(generate_assistant(), media_type="text/event-stream")

        # --- FLUJO NORMAL (Sonora General - Chat Completions) ---
        # Llamada a OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini", # O gpt-4o si queremos mejor visión, pero mini es más rápido/barato y tiene visión
            messages=[
                {"role": "system", "content": get_system_prompt(pilar_id)},
                {"role": "user", "content": openai_content}
            ],
            stream=True
        )

        # Streaming de respuesta
        async def generate():
            full_response = ""
            try:
                loop = asyncio.get_event_loop()
                queue: asyncio.Queue = asyncio.Queue()

                def _stream_to_queue():
                    try:
                        for chunk in response:
                            content = chunk.choices[0].delta.content
                            if content:
                                loop.call_soon_threadsafe(queue.put_nowait, content)
                        loop.call_soon_threadsafe(queue.put_nowait, None)
                    except Exception as e:
                        loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))

                import threading
                threading.Thread(target=_stream_to_queue, daemon=True).start()

                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    full_response += item
                    yield f"data: {json.dumps({'content': item})}\n\n"
                    await asyncio.sleep(0)

                db_service.add_message("agent", full_response)
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Error en streaming upload: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream",
                                  headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


    except Exception as e:
        logger.error(f"Error en upload: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 