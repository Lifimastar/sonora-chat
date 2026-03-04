"""
Servicio para interactuar con Supabase y guardar el historial de chat.
"""
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from loguru import logger
from supabase import create_client, Client
from app.core.supabase_client import get_supabase

load_dotenv()

class DatabaseService:
    def __init__(self):
        self.client: Client = get_supabase()
        self.conversation_id = None
        self.user_id = None
    
    def create_conversation(self, title: str = "Nueva conversacion", user_id: str = None):
        """Crea una nueva sesion de conversacion"""
        data = {
            "title": title,
            "metadata": {"source": "pipecat_bot"}
        }

        if user_id:
            data["user_id"] = user_id

        response = self.client.table("conversations").insert(data).execute()

        if response.data:
            self.conversation_id = response.data[0]['id']
            logger.info(f"📝 Conversacion iniciada: {self.conversation_id} (Usuario: {user_id})")
            return self.conversation_id
        return None
    
    
    def add_message(self, role: str, content: str, images: list = None):
        """Guarda un mensaje en la conversacion actual (soporta imagenes)"""
        if not self.conversation_id:
            logger.warning("⚠️ No hay conversacion activa. Creando una nueva automaticamente...")
            self.create_conversation(title="Conversacion Automatica", user_id=self.user_id)
            if not self.conversation_id:
                logger.error("No se pudo crear la conversacion")
                return
        
        data = {
            "conversation_id": self.conversation_id,
            "role": role,
            "content": content,
            "images": images if images else [] # Guardar URLs de imagenes
        }
        try:
            self.client.table("messages").insert(data).execute()
            logger.debug(f"💾 mensaje guardado ({role}) - Imgs: {len(images) if images else 0}")
        except Exception as e:
            logger.error(f"❌ error guardando mensaje: {e}")
    
    def get_history(self, limit: int = 50):
        """Recupera el historial (para futuras implementaciones de 'continuar')"""
        if not self.conversation_id:
            return []
        
        response = self.client.table("messages").select("*").eq("conversation_id", self.conversation_id).order("created_at", desc=False).limit(limit).execute()

        return response.data
    
    def get_conversation_history(self, conversation_id: str):
        """Recupera el historial formateado para el LLM"""
        try:
            # Ahora traemos tambien 'images'
            response = self.client.table("messages").select("role, content, images").eq("conversation_id", conversation_id).is_("deleted_at", "null").order("created_at").execute()

            formatted_history = []
            if response.data:
                for msg in response.data:
                    role = "assistant" if msg["role"] == "agent" else msg["role"]
                    content = msg["content"]
                    images = msg.get("images", [])

                    # Si hay imágenes y es mensaje de usuario, construimos payload multimodal
                    if role == "user" and images and len(images) > 0:
                        content_payload = [{"type": "text", "text": content}]
                        for img_url in images:
                            content_payload.append({
                                "type": "image_url",
                                "image_url": {"url": img_url}
                            })
                        
                        formatted_history.append({
                            "role": role,
                            "content": content_payload
                        })
                    else:
                        # Texto normal
                        # Si es asistente y tenía imágenes (raro en este flujo pero posible), las mencionamos
                        if role == "assistant" and images:
                             content += f"\n[El asistente generó {len(images)} imágenes]"

                        formatted_history.append({
                            "role": role,
                            "content": content
                        })

            return formatted_history
        except Exception as e:
            logger.error(f"❌ Error recuperando historial: {e}")
            return []

    def save_memory(self, key: str, value: str, user_id: str = None):
        """
        Guarda un dato persistente.
        - Si user_id es None -> Memoria Global (shared_memory)
        - Si user_id tiene valor -> Memoria Usuario (user_memory)
        """
        try:
            if user_id:
                # Memoria de Usuario
                data = {
                    "user_id": user_id,
                    "key": key,
                    "value": value
                }
                # Upsert en user_memory
                # OJO: user_memory pkey es 'id' (autoincrement). Necesitamos unique constraint en (user_id, key) para upsert correcto.
                # Asumimos que la tabla tiene logicamente esa unicidad. Si no, hacemos delete+insert o check.
                # Para simplificar con Supabase:
                # Vamos a intentar borrar previo y luego insertar, o usar upsert con on_conflict si existe el index.
                
                # Check if exists
                existing = self.client.table("user_memory").select("id").eq("user_id", user_id).eq("key", key).execute()
                if existing.data:
                    # Update
                    self.client.table("user_memory").update({"value": value}).eq("id", existing.data[0]['id']).execute()
                else:
                    # Insert
                    self.client.table("user_memory").insert(data).execute()
                
                logger.info(f"🧠 Memoria USUARIO guardada: {key} = {value} ({user_id})")
            else:
                # Memoria Global
                data = {"key": key, "value": value}
                self.client.table("shared_memory").upsert(data, on_conflict="key").execute()
                logger.info(f"🌍 Memoria GLOBAL guardada: {key} = {value}")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error guardando memoria ({'user' if user_id else 'global'}): {e}")
            return False
    
    def get_all_memories(self, user_id: str = None):
        """Recupera todas las memorias (Globales + Usuario si existe)"""
        memories = {}
        try:
            # 1. Globales
            response_shared = self.client.table("shared_memory").select("key, value").execute()
            for item in response_shared.data:
                memories[f"GLOBAL_{item['key']}"] = item['value']
            
            # 2. Usuario (si aplica)
            if user_id:
                response_user = self.client.table("user_memory").select("key, value").eq("user_id", user_id).execute()
                for item in response_user.data:
                    memories[f"USER_{item['key']}"] = item['value']
                    
            return memories
        except Exception as e:
            logger.error(f"Error recuperando memorias: {e}")
            return {}
        
    def delete_memory(self, key: str, user_id: str = None):
        """Borra un dato persistente (intenta en ambos si no se especifica, o prioriza usuario)"""
        try:
            deleted = False
            # Intentar borrar de usuario primero si hay ID
            if user_id:
                res = self.client.table("user_memory").delete().eq("user_id", user_id).eq("key", key).execute()
                if res.data:
                    logger.info(f"🗑️ Memoria USUARIO borrada: {key}")
                    deleted = True
            
            # Si no se borró de usuario (o no habia user_id), intentar global
            # PERO: si el usuario quiere borrar algo global, ¿le dejamos?
            # Asumamos que 'borrar_dato' en BotTools maneja permisos. 
            # Aquí la función es genérica.
            if not deleted:
                res = self.client.table("shared_memory").delete().eq("key", key).execute()
                if res.data:
                    logger.info(f"🗑️ Memoria GLOBAL borrada: {key}")
                    deleted = True
            
            return deleted
        except Exception as e:
            logger.error(f"❌ Error borrando memoria: {e}")
            return False

    def get_activity_stats(self, tipo: str = "resumen_general") -> dict:
        """Obtiene estadísticas de actividad del ecosistema."""
        try:
            now = datetime.now(timezone.utc)
            
            if tipo == "resumen_general":
                # Total conversaciones
                convos = self.client.table("conversations").select("id", count="exact").execute()
                total_convos = convos.count if convos.count is not None else len(convos.data)
                
                # Total mensajes
                msgs = self.client.table("messages").select("id", count="exact").execute()
                total_msgs = msgs.count if msgs.count is not None else len(msgs.data)
                
                # Usuarios distintos (de conversations)
                users_data = self.client.table("conversations").select("user_id").not_.is_("user_id", "null").execute()
                unique_users = len(set(row["user_id"] for row in users_data.data)) if users_data.data else 0
                
                # Documentos en knowledge base
                kb = self.client.table("knowledge_base").select("id", count="exact").execute()
                total_kb = kb.count if kb.count is not None else len(kb.data)
                
                return {
                    "success": True,
                    "tipo": "Resumen General",
                    "total_conversaciones": total_convos,
                    "total_mensajes": total_msgs,
                    "usuarios_distintos": unique_users,
                    "documentos_knowledge_base": total_kb,
                }

            elif tipo in ("actividad_hoy", "actividad_semana", "actividad_mes"):
                if tipo == "actividad_hoy":
                    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    label = "Hoy"
                elif tipo == "actividad_semana":
                    since = now - timedelta(days=7)
                    label = "Últimos 7 días"
                else:
                    since = now - timedelta(days=30)
                    label = "Últimos 30 días"
                
                since_iso = since.isoformat()
                
                # Conversaciones en el período
                convos = self.client.table("conversations").select("id", count="exact").gte("created_at", since_iso).execute()
                period_convos = convos.count if convos.count is not None else len(convos.data)
                
                # Mensajes en el período
                msgs = self.client.table("messages").select("id", count="exact").gte("created_at", since_iso).execute()
                period_msgs = msgs.count if msgs.count is not None else len(msgs.data)
                
                # Usuarios activos en el período
                users_data = self.client.table("conversations").select("user_id").not_.is_("user_id", "null").gte("created_at", since_iso).execute()
                active_users = len(set(row["user_id"] for row in users_data.data)) if users_data.data else 0
                
                return {
                    "success": True,
                    "tipo": f"Actividad — {label}",
                    "periodo": label,
                    "conversaciones": period_convos,
                    "mensajes": period_msgs,
                    "usuarios_activos": active_users,
                }
            
            else:
                return {"success": False, "error": f"Tipo de reporte no reconocido: {tipo}"}
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {"success": False, "error": str(e)}