#import os
#from supabase import create_client, Client
#from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import Counter
from loguru import logger
from app.core.supabase_client import get_tuguia_supabase

class TuGuiaDatabase:
    """Servicio para interactuar con la base de datos de Tu Guia"""

    def __init__(self):
        self.client = get_tuguia_supabase()
    
    def count_users(self):
        """Cuenta usuarios en la base de datos de Tu Guia"""
        try:
            response = self.client.table("profiles").select("id", count="exact").limit(0).execute()
            return response.count or 0
        except Exception as e:
            logger.error(f"Error contando usuarios de Tu Guia: {e}")
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

    def get_basic_metrics(self) -> dict:
        """
        Obtiene metricas basicas consolidadas de Tu Guia Argentina.
        Retorna totales, suscripciones, verificados, registros recientes,
        servicios publicados y top provincias.
        """
        try:
            now = datetime.now(timezone.utc)
            d7 = (now - timedelta(days=7)).isoformat()
            d30 = (now - timedelta(days=30)).isoformat()

            # Total perfiles
            total_res = self.client.table("profiles").select("id", count="exact").limit(0).execute()
            total_profiles = total_res.count or 0

            # Suscripciones
            active_res = self.client.table("profiles").select("id", count="exact").eq("subscription_status", "active").limit(0).execute()
            inactive_res = self.client.table("profiles").select("id", count="exact").eq("subscription_status", "inactive").limit(0).execute()
            subs_active = active_res.count or 0
            subs_inactive = inactive_res.count or 0

            # Tipo de cuenta
            personal_res = self.client.table("profiles").select("id", count="exact").eq("account_type", "personal").limit(0).execute()
            business_res = self.client.table("profiles").select("id", count="exact").eq("account_type", "business").limit(0).execute()
            acc_personal = personal_res.count or 0
            acc_business = business_res.count or 0

            # Verificados
            verified_res = self.client.table("profiles").select("id", count="exact").eq("verified", True).limit(0).execute()
            not_verified_res = self.client.table("profiles").select("id", count="exact").eq("verified", False).limit(0).execute()
            verified = verified_res.count or 0
            not_verified = not_verified_res.count or 0

            # Registros recientes
            signups_7d_res = self.client.table("profiles").select("id", count="exact").gte("created_at", d7).limit(0).execute()
            signups_30d_res = self.client.table("profiles").select("id", count="exact").gte("created_at", d30).limit(0).execute()
            signups_7d = signups_7d_res.count or 0
            signups_30d = signups_30d_res.count or 0

            # Servicios publicados
            services_res = self.client.table("services").select("id", count="exact").limit(0).execute()
            total_services = services_res.count or 0

            # Top provincias (hasta 5)
            addr_res = self.client.table("addresses").select("province").execute()
            top_provinces = []
            if addr_res.data:
                provs = Counter(x["province"] for x in addr_res.data if x.get("province"))
                top_provinces = [{"province": p, "count": c} for p, c in provs.most_common(5)]

            return {
                "success": True,
                "total_profiles": total_profiles,
                "subscriptions": {
                    "active": subs_active,
                    "inactive": subs_inactive,
                },
                "account_types": {
                    "personal": acc_personal,
                    "business": acc_business,
                },
                "verification": {
                    "verified": verified,
                    "not_verified": not_verified,
                },
                "signups": {
                    "last_7d": signups_7d,
                    "last_30d": signups_30d,
                },
                "total_services": total_services,
                "top_provinces": top_provinces,
            }

        except Exception as e:
            logger.error(f"Error obteniendo metricas de Tu Guia: {e}")
            return {"success": False, "error": str(e)}

    def get_adheridos_metrics(self) -> dict:
        """
        Obtiene metricas de adheridos (profiles con role=member):
        - Total de adheridos
        - Adheridos por rubro (subcategoria)
        - Adheridos por provincia
        """
        try:
            # Total adheridos
            total_res = self.client.table("profiles").select("id", count="exact").eq("role", "member").limit(0).execute()
            total_adheridos = total_res.count or 0

            # IDs de adheridos
            members_res = self.client.table("profiles").select("id").eq("role", "member").execute()
            member_ids = [m["id"] for m in members_res.data] if members_res.data else []

            # Adheridos por rubro (subcategoria)
            rubros = {}
            if member_ids:
                ps_res = self.client.table("profile_subcategories").select(
                    "profile_id, subcategories(name)"
                ).in_("profile_id", member_ids).execute()

                if ps_res.data:
                    for row in ps_res.data:
                        sub = row.get("subcategories")
                        if sub and sub.get("name"):
                            name = sub["name"]
                            rubros[name] = rubros.get(name, 0) + 1

            rubros_sorted = sorted(rubros.items(), key=lambda x: -x[1])

            # Adheridos por provincia
            provincias = {}
            if member_ids:
                addr_res = self.client.table("addresses").select(
                    "user_id, province"
                ).in_("user_id", member_ids).execute()

                if addr_res.data:
                    for row in addr_res.data:
                        prov = row.get("province")
                        if prov:
                            provincias[prov] = provincias.get(prov, 0) + 1

            provincias_sorted = sorted(provincias.items(), key=lambda x: -x[1])

            return {
                "success": True,
                "total_adheridos": total_adheridos,
                "por_rubro": [{"rubro": r, "count": c} for r, c in rubros_sorted],
                "por_provincia": [{"provincia": p, "count": c} for p, c in provincias_sorted],
            }

        except Exception as e:
            logger.error(f"Error obteniendo metricas de adheridos: {e}")
            return {"success": False, "error": str(e)}
