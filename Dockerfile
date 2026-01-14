FROM python:3.11-slim

WORKDIR /app

# Instalar uv
RUN pip install uv

# Copiar archivos de dependencias
COPY pyproject.toml ./

# Instalar dependencias
RUN uv sync --no-dev

# Copiar código
COPY app ./app

# Puerto
EXPOSE 7861

# Comando
CMD ["uv", "run", "python", "-m", "app.api.server"]
