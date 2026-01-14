"""
Processor para capturar frames de video y pasarlos a GPT-4o.
"""
import base64
import asyncio
import io
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, UserImageRawFrame
from loguru import logger

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("PIL no instalado. Las imagenes no se comprimiran.")

class VisionCaptureProcessor(FrameProcessor):
    """
    Captura frames de video del usuario, los comprime, y los almacena
    para que puedan ser incluidos en el contexto del LLM.
    """

    def __init__(self, capture_interval: float = 2.0, max_size: int = 512, quality: int = 60):
        super().__init__()
        self._last_image: bytes | None = None
        self._last_image_base64: str | None = None
        self._capture_interval = capture_interval
        self._last_capture_time = 0
        self._max_size = max_size
        self._quality = quality
        logger.info(f"📷 VisionCaptureProcessor inicializado (intervalo: {capture_interval}s, max_size: {max_size}px, quality: {quality})")
    
    def _compress_image(self, frame: UserImageRawFrame) -> str:
        """Comprime la iamgen raw y retorna base64."""
        if not HAS_PIL:
            return base64.b64encode(frame.image).decode('utf-8')
        
        try:
            width, height = frame.size
            
            mode = 'RGBA' if len(frame.image) == width * height * 4 else 'RGB'
            img = Image.frombytes(mode, (width, height), frame.image)

            if img.mode == 'RGBA':
                img = img.convert('RGB')

            if width > self._max_size or height > self._max_size:
                ratio = min(self._max_size / width, self._max_size / height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                #logger.debug(f"Imagen redimensionada a {new_size}")
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=self._quality, optimize=True)
            compressed_bytes = buffer.getvalue()

            #logger.debug(f"Imagen comprimida: {len(frame.image)} -> {len(compressed_bytes)} bytes")

            return base64.b64encode(compressed_bytes).decode('utf-8')

        except Exception as e:
            logger.error(f"Error comprimiendo imagen: {e}")
            return None
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserImageRawFrame):
            current_time = asyncio.get_event_loop().time()

            if current_time - self._last_capture_time >= self._capture_interval:
                self._last_image = frame.image
                self._last_image_base64 = self._compress_image(frame)
                self._last_capture_time = current_time
                #logger.debug(f"Frame capturado y comprimido")
        
        await self.push_frame(frame, direction)
    
    def get_last_image_base64(self) -> str | None:
        """Retorna la última imagen capturada (comprimida) en formato base64."""
        return self._last_image_base64
    
    def has_image(self) -> bool:
        """Verifica si hay una imagen disponible."""
        return self._last_image is not None