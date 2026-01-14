from loguru import logger
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.pipeline.task import PipelineTask
from pipecat.frames.frames import LLMRunFrame, StartInterruptionFrame
from app.services.database import DatabaseService

class ConversationActionHandler:
    def __init__(self, db_service: DatabaseService, context: LLMContext):
        self.db_service = db_service
        self.context = context
        self.task: PipelineTask | None = None

    def set_task(self, task: PipelineTask):
        self.task = task

    async def handle_action(self, processor, service, arguments):
        conversation_id = arguments.get("conversation_id")
        user_id = arguments.get("user_id")

        if user_id:
            logger.info(f"Configurando usuario: {user_id}")
            # Importar aquí para evitar probelas de referencia circular si las hubiera
            from app.context import current_user_id
            current_user_id.set(user_id)
            self.db_service.user_id = user_id
            #self.db_service.ensure_user_exists(user_id)
        
        logger.info(f"🔄 Configurando conversación: {conversation_id}")

        memories = self.db_service.get_all_memories(user_id=self.db_service.user_id)
        if memories:
            memory_list = [f"- {k}: {v}" for k, v in memories.items()]
            memory_text = "\nDATOS RECORDADOS:\n" + "\n".join(memory_list)
            logger.info(f"Memorias cargadas: {len(memories)} (Usuario: {self.db_service.user_id})")
        
            self.context.add_message({
                "role": "system",
                "content": f"Informacion persistente que debe recordar:\n{memory_text}"
            })
        
        messages_to_send = []
        
        if conversation_id:
            # CASO 1: Reanudar conversación existente
            self.db_service.conversation_id = conversation_id
            logger.info("✅ ID de conversación establecido.")
            
            # Cargar historial
            history = self.db_service.get_conversation_history(conversation_id)
            
            if history:
                logger.info(f"📜 Inyectando {len(history)} mensajes al contexto")
                # Inyectar historial en el contexto del LLM
                for msg in history:
                    self.context.add_message({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
                
                # Saludo de re-conexión
                messages_to_send = [
                    {"role": "system", "content": "El usuario ha vuelto. Saluda brevemente (ej: 'Hola de nuevo') y pregunta en qué quedaron."}
                ]
            else:
                 messages_to_send = [{"role": "system", "content": "Saluda al usuario."}]

        else:
            # CASO 2: Nueva conversación
            logger.info("✨ Iniciando nueva sesión.")
            self.db_service.conversation_id = None # Asegurar que esté limpio
            messages_to_send = [
                {"role": "system", "content": "Saluda brevemente como asistente de Red Futura."}
            ]

        # Disparar el saludo AHORA
        if messages_to_send:
            logger.info(f"📨 Enviando instrucciones al LLM: {messages_to_send}")
            for msg in messages_to_send:
                self.context.add_message(msg)
            
            if self.task:
                await self.task.queue_frame(LLMRunFrame())
            else:
                logger.error("❌ Task no seteado en ConversationActionHandler, no se puede enviar LLMRunFrame")
        
        return True

    async def handle_user_image(self, image_base64: str):
        """Maneja imagenes subidas por el usuario (Legacy single image)."""
        if not image_base64:
            return
        
        logger.info(f"Recibida imagen del usuario (Legacy).")

        self.context.add_message({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "He subido una imagen. Analizala."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_base64
                    }
                }
            ]
        })

        if self.task:
            await self.task.queue_frame(LLMRunFrame())
        else:
            logger.error("Task no disponible para procesar imagen")

    async def handle_multimodal_message(self, text: str, image_urls: list):
        """Maneja mensajes compuestos de texto + multiples imagenes (via URL)."""
        logger.info(f"📸 Procesando mensaje multimodal: '{text}' + {len(image_urls)} imagenes")

        if self.task:
            await self.task.queue_frame(StartInterruptionFrame())

        content_block = []
        
        # 1. Agregar el texto
        if text:
            content_block.append({"type": "text", "text": text})
        
        # 2. Agregar las imágenes
        for url in image_urls:
            content_block.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
            
        # 3. Guardar en Contexto del LLM
        self.context.add_message({
            "role": "user",
            "content": content_block
        })
        
        # 4. Guardar en Base de Datos (Persistencia)
        # Usamos el servicio de DB para guardar el registro
        self.db_service.add_message("user", text, images=image_urls)

        # 5. Disparar respuesta del LLM
        if self.task:
             await self.task.queue_frame(LLMRunFrame())
        else:
            logger.error("❌ Task no disponible para procesar mensaje multimodal")

    async def handle_file_message(self, text: str, file_content: str, file_name: str):
        """Maneja mensajes con archivos de texto adjuntos."""
        logger.info(f"Procesando archivo: '{file_name}' ({len(file_content) if file_content else 0}) chars")

        if self.task:
            await self.task.queue_frame(StartInterruptionFrame())

        if not file_content:
            logger.warning("Archivo vacio recibido")
            return
        
        # Trunca si es muy largo (limite de tokens)
        MAX_CHARS = 15000 # ~4000 tokens
        truncated = False
        if len(file_content) > MAX_CHARS:
            file_content = file_content[:MAX_CHARS]
            truncated = True
        
        # Contruir mensaje para el LLM
        truncation_note = "\n\n[... contenido truncado por longitud ...]" if truncated else ""
        user_message = f"""El usuario ha compartido un archivo llamado "{file_name}".
        CONTENIDO DEL ARCHIVO:
        ---
        {file_content}{truncation_note}
        ---
        MENSAJE DEL USUARIO {text if text else "Analiza este archivo."}"""

        self.context.add_message({
            "role": "user",
            "content": user_message
        })

        # Guardar en DB
        self.db_service.add_message("user", f"[Archivo: {file_name}] {text if text else ''}")

        # Disparar respuesta
        if self.task:
            await self.task.queue_frame(LLMRunFrame())
        else:
            logger.error("Task no disponible para procesar archivo")