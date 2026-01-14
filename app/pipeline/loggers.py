"""
Processors de Pipecat para interceptar y guardar mensajes.
"""
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import TranscriptionFrame, TextFrame, LLMFullResponseEndFrame, EndFrame
from app.services.database import DatabaseService

class UserLogger(FrameProcessor):
    def __init__(self, db_service):
        super().__init__()
        self.db = db_service
    
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            if frame.text.strip():
                self.db.add_message("user", frame.text)
        await self.push_frame(frame, direction)

class AssistantLogger(FrameProcessor):
    def __init__(self, db_service):
        super().__init__()
        self.db = db_service
        self._buffer = ""
    
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TextFrame):
            self._buffer += frame.text
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._buffer.strip():
                self.db.add_message("assistant", self._buffer)
                self._buffer = ""
        await self.push_frame(frame, direction)