from contextvars import ContextVar

current_user_id = ContextVar("current_user_id", default=None)