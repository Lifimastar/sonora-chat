import requests
import json
import sys

# Test query that previously failed for users without a Pilar
payload = {
    "message": "ahora decime la tabla de comisiones que utilizamos para pagarle al asesor comercial ?",
    "conversation_id": "test_verification",
    "pilar_id": None
}

print("Iniciando peticion POST a /api/chat sin pilar_id...")
try:
    response = requests.post("http://localhost:7861/api/chat", json=payload, stream=True)
    for line in response.iter_lines():
        if line:
            print(line.decode("utf-8"))
except Exception as e:
    print(f"Error HTTP: {e}")
