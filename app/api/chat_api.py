"""
API HTTP para chat de texto.
Usa la misma lógica del bot de voz (OpenAI + Tools).
"""
import os
import json
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
from loguru import logger

from app.services.database import DatabaseService
from app.services.rag import get_relevant_context
from app.services.tuguia_database import TuGuiaDatabase
from app.prompts import SYSTEM_PROMPT

router = APIRouter()

# Cliente OpenAI
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=30.0
)

class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    user_id: Optional[str] = None
    camera_image: Optional[str] = None  # Imagen base64 de la cámara

# Definir las tools para el LLM (mismas que en bot.py)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_informacion",
            "description": "Busca información en la base de conocimiento sobre contratos, términos y condiciones.",
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
            "description": "Guarda un dato en la memoria persistente.",
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
    }
]

def execute_tool(tool_name: str, arguments: dict, db_service: DatabaseService, user_id: str = None) -> dict:
    """Ejecuta una tool y retorna el resultado."""
    try:
        if tool_name == "buscar_informacion":
            query = arguments.get("query", "")
            context = get_relevant_context(query)
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
    return f"\n\nMEMORIA DEL USUARIO:\n{memory_text}"

@router.post("/chat")
async def chat(request: ChatRequest):
    """Endpoint principal de chat."""
    db_service = DatabaseService()
    db_service.conversation_id = request.conversation_id
    db_service.user_id = request.user_id
    
    try:
        # 1. Guardar mensaje del usuario
        db_service.add_message("user", request.message)
        
        # 2. Obtener contexto
        history = get_conversation_history(request.conversation_id, db_service)
        memory = get_user_memory(request.user_id, db_service) if request.user_id else ""
        
        # 3. Construir mensajes
        system_content = SYSTEM_PROMPT + """

NOTA: Estás respondiendo en modo TEXTO (no voz).
- Puedes usar formato markdown si mejora la legibilidad.
- Puedes usar listas con viñetas o numeradas.
- Puedes usar negritas para enfatizar puntos importantes."""
        
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
                    result = execute_tool(tool_name, arguments, db_service, request.user_id)
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
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"
                
                # Guardar respuesta del bot
                db_service.add_message("agent", full_response)
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Error en streaming: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    user_id: str = Form(None),
    message: str = Form(""),
    image_urls: str = Form("")  # URLs de imágenes separadas por coma
):
    """Endpoint para subir archivos con mensaje opcional."""
    db_service = DatabaseService()
    db_service.conversation_id = conversation_id
    db_service.user_id = user_id

    try:
        # Leer archivo
        file_content = await file.read()

        MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Archivo muy grande. Maximo 10MB.")

        file_name = file.filename
        file_type = file.content_type

        logger.info(f"📁 Archivo recibido: {file_name} (MIME: {file_type})")

        # Extraer texto segun tipo
        text_content = ""
        if file_type and file_type.startswith("image/"):
            # Para imagenes, las procesamos como base64
            import base64
            image_base64 = base64.b64encode(file_content).decode("utf-8")

            # Guardar mensaje del usuario con referencia a imagen
            user_msg = message if message else f"[Imagen: {file_name}]"
            # Parsear URLs de imágenes
            img_list = [url.strip() for url in image_urls.split(",") if url.strip()] if image_urls else []
            db_service.add_message("user", user_msg, images=img_list)

            # Llamar a OpenAI con la imagen
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": message if message.strip() else "Describe brevemente esta imagen y pregunta al usuario qué quiere saber sobre ella o qué quiere hacer con ella."},
                        {"type": "image_url", "image_url": {"url": f"data:{file_type};base64,{image_base64}"}}
                    ]}
                ],
                stream=True
            )
        elif file_type in ["text/plain", "text/markdown"] or (file_name and file_name.lower().endswith((".txt", ".md", ".json"))):
            text_content = file_content.decode("utf-8")
            user_msg = f"{message}\n📄 [Archivo adjunto: {file_name}]"
            db_service.add_message("user", user_msg)

            # Llamar a OpenAI con el texto
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"{message}\n\nContenido del archivo {file_name}:\n{text_content}"}
                ],
                stream=True
            )
        else:
            return {"error": f"Tipo de archivo no soportado: {file_type}"}

        # Streaming de respuesta
        async def generate():
            full_response = ""
            try:
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"
                
                # Guardar respuesta del bot
                db_service.add_message("agent", full_response)
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Error en streaming upload: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Error en upload: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 