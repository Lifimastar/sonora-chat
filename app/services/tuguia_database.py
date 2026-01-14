#import os
#from supabase import create_client, Client
#from dotenv import load_dotenv
from app.core.supabase_client import get_tuguia_supabase

class TuGuiaDatabase:
    """Servicio para interactuar con la base de datos de Tu Guia"""

    def __init__(self):
        self.client = get_tuguia_supabase()
    
    def count_users(self):
        """Cuenta usuarios en la base de datos de Tu Guia"""
        try:
            # Asumiendo que la tabla se llama 'users' o 'usuarios
            # Ajusta el nombre segun tu esquema
            response = self.client.auth.admin.list_users()

            if hasattr(response, 'users'):
                return len(response.users)
            elif isinstance(response, list):
                return len(response)
            else:
                return 0
        except Exception as e:
            print(f"Error contando usuarios de Tu Guia: {e}")
            return None
    
    def create_user(self, email: str, password: str, first_name: str, last_name: str, phone: str, account_type: str):
        """
        Crea un usuario en Tu Guía usando Supabase Auth
    
        Args:
            email: Correo electrónico
            password: Contraseña
            first_name: Nombre
            last_name: Apellido
            phone: Teléfono
            account_type: Tipo de cuenta (ej: "cliente", "proveedor")
        """
        try:
            response = self.client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                "full_name": f"{first_name} {last_name}",
                "phone": phone,
                "account_type": account_type
            }
            })

            if hasattr(response, 'user') and response.user:
                return {
                    "success": True,
                    "user_id": response.user.id,
                "email": email,
                "full_name": f"{first_name} {last_name}"
            }
            else:
                return {
                    "success": False,
                    "error": "No se pudo crear el usuario"
                }
        
        except Exception as e:
            print(f"Error creando usuario en Tu Guia: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def count_users_by_subcategory(self, subcategory_names):
        """
        Cuenta usuarios por subcategorias especificas

        Args:
            subcategory_names: Lista de nombres de subcategorias o un solo nombre (string)

        Returns:
            Dict con conteo por subcategoria
        """
        try:
            # Convertir a lista si es un solo string
            if isinstance(subcategory_names, str):
                subcategory_names = [subcategory_names]
            
            results = {}
            
            for subcategory_name in subcategory_names:
                # buscar subcategoria por nombre
                subcategory_response = self.client.table('subcategories').select('id', 'name').ilike('name', f'%{subcategory_name}%').execute()

                if not subcategory_response.data:
                    results[subcategory_name] = {
                        "found": False,
                        "count": 0,
                        "error": "No encontrada"
                    }
                    continue

                # Tomar la primera coincidencia
                subcat = subcategory_response.data[0]

                # contar perfiles en esa subcategoria
                count_response = self.client.table('profile_subcategories').select('profile_id', count='exact').eq('subcategory_id', subcat['id']).execute()

                results[subcat['name']] = {
                    "found": True,
                    "count": count_response.count or 0
                }
            
            return {
                    "success": True,
                    "results": results
                }
        
        except Exception as e:
            print(f"Error contando usuarios por subcategoria en Tu Guia: {e}")
            return {
                "success": False,
                "error": str(e)
            }
