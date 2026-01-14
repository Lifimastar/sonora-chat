import secrets
import string

def generar_password_segura(longitud=16):
    """Genera una contrasena segura aleatoria."""
    caracteres = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(secrets.choice(caracteres) for _ in range(longitud))
    return password
