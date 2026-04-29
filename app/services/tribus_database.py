"""
Servicio de datos para la IA Jefa de Tribu (Pilar 3).
Consulta leads de Marketplace (tabla marketplace_leads en Sonora DB)
y asesores comerciales (tabla profiles en TuGuía DB).

NOTA: Este servicio SOLO LEE datos. La escritura de leads
la hace el repo separado bot-marketplace-facebook.
"""
from loguru import logger
from app.core.supabase_client import get_supabase, get_tuguia_supabase


class TribusDatabase:
    """Servicio unificado para consultas de la IA Jefa de Tribu."""

    def __init__(self):
        self.sonora_client = get_supabase()
        self.tuguia_client = get_tuguia_supabase()

    def consultar_leads(self, rubro: str = None, provincia: str = None, estado: str = None) -> dict:
        """
        Consulta leads de Marketplace con filtros opcionales.
        Usada por la tool 'consultar_leads_marketplace'.
        """
        try:
            query = self.sonora_client.table("marketplace_leads").select("*")
            
            if rubro:
                query = query.ilike("rubro", f"%{rubro}%")
            if provincia:
                query = query.ilike("provincia", f"%{provincia}%")
            if estado:
                query = query.eq("estado", estado)
            
            result = query.order("created_at", desc=True).limit(50).execute()
            
            # Contar total con filtros
            total_query = self.sonora_client.table("marketplace_leads").select("id", count="exact")
            if rubro:
                total_query = total_query.ilike("rubro", f"%{rubro}%")
            if provincia:
                total_query = total_query.ilike("provincia", f"%{provincia}%")
            if estado:
                total_query = total_query.eq("estado", estado)
            total_result = total_query.limit(0).execute()
            total = total_result.count or 0
            
            # Contar con teléfono
            phone_query = self.sonora_client.table("marketplace_leads") \
                .select("id", count="exact") \
                .not_.is_("telefono", "null")
            if rubro:
                phone_query = phone_query.ilike("rubro", f"%{rubro}%")
            if provincia:
                phone_query = phone_query.ilike("provincia", f"%{provincia}%")
            phone_result = phone_query.limit(0).execute()
            con_telefono = phone_result.count or 0
            
            leads_preview = []
            for lead in (result.data or [])[:20]:
                leads_preview.append({
                    "nombre": lead.get("nombre", "Sin nombre"),
                    "telefono": lead.get("telefono", "N/A"),
                    "rubro": lead.get("rubro"),
                    "ciudad": lead.get("ciudad"),
                    "provincia": lead.get("provincia"),
                    "estado": lead.get("estado"),
                })
            
            filtros_aplicados = []
            if rubro:
                filtros_aplicados.append(f"rubro={rubro}")
            if provincia:
                filtros_aplicados.append(f"provincia={provincia}")
            if estado:
                filtros_aplicados.append(f"estado={estado}")
            
            return {
                "success": True,
                "total": total,
                "con_telefono": con_telefono,
                "sin_telefono": total - con_telefono,
                "filtros": ", ".join(filtros_aplicados) if filtros_aplicados else "ninguno",
                "muestra": leads_preview,
            }
        except Exception as e:
            logger.error(f"Error consultando leads: {e}")
            return {"success": False, "error": str(e)}

    def medir_asesores(self) -> dict:
        """
        Obtiene métricas de los asesores comerciales desde TuGuía.
        Usada por la tool 'medir_asesores_tribu'.
        """
        try:
            result = self.tuguia_client.table("profiles") \
                .select("id, full_name, phone, role, account_type, created_at") \
                .eq("role", "sales_advisor") \
                .execute()
            
            asesores = result.data or []
            
            return {
                "success": True,
                "total_asesores": len(asesores),
                "asesores": [
                    {
                        "nombre": a.get("full_name", "Sin nombre"),
                        "telefono": a.get("phone"),
                        "rol": a.get("role"),
                        "tipo_cuenta": a.get("account_type"),
                        "fecha_registro": a.get("created_at"),
                    }
                    for a in asesores
                ]
            }
        except Exception as e:
            logger.error(f"Error obteniendo asesores: {e}")
            return {"success": False, "error": str(e)}

    def ver_resumen_zona(self) -> dict:
        """
        Resumen completo de la zona: leads por rubro, por estado,
        con y sin teléfono, y cantidad de asesores.
        Usada por la tool 'ver_resumen_zona'.
        """
        try:
            # Leads
            total_res = self.sonora_client.table("marketplace_leads").select("id", count="exact").limit(0).execute()
            total_leads = total_res.count or 0
            
            phone_res = self.sonora_client.table("marketplace_leads") \
                .select("id", count="exact").not_.is_("telefono", "null").limit(0).execute()
            con_telefono = phone_res.count or 0
            
            # Por rubro
            rubro_res = self.sonora_client.table("marketplace_leads").select("rubro").execute()
            por_rubro = {}
            for row in (rubro_res.data or []):
                r = row["rubro"]
                por_rubro[r] = por_rubro.get(r, 0) + 1
            
            # Por estado
            estado_res = self.sonora_client.table("marketplace_leads").select("estado").execute()
            por_estado = {}
            for row in (estado_res.data or []):
                e = row["estado"]
                por_estado[e] = por_estado.get(e, 0) + 1
            
            # Asesores
            asesor_res = self.tuguia_client.table("profiles") \
                .select("id", count="exact").eq("role", "sales_advisor").limit(0).execute()
            total_asesores = asesor_res.count or 0
            
            return {
                "success": True,
                "leads": {
                    "total": total_leads,
                    "con_telefono": con_telefono,
                    "sin_telefono": total_leads - con_telefono,
                    "por_rubro": por_rubro,
                    "por_estado": por_estado,
                },
                "asesores": {
                    "total": total_asesores,
                },
            }
        except Exception as e:
            logger.error(f"Error obteniendo resumen de zona: {e}")
            return {"success": False, "error": str(e)}

    def asignar_leads(self, rubro: str, asesor_nombre: str, cantidad: int = 10) -> dict:
        """
        Asigna un lote de leads sin asignar a un asesor.
        Usada por la tool 'asignar_leads_a_asesor'.
        """
        try:
            # Buscar al asesor en TuGuía por nombre
            asesor_result = self.tuguia_client.table("profiles") \
                .select("id, full_name") \
                .eq("role", "sales_advisor") \
                .ilike("full_name", f"%{asesor_nombre}%") \
                .limit(1) \
                .execute()
            
            if not asesor_result.data:
                return {
                    "success": False,
                    "error": f"No se encontró un asesor con nombre '{asesor_nombre}'"
                }
            
            asesor = asesor_result.data[0]
            asesor_id = asesor["id"]
            asesor_full_name = asesor["full_name"]
            
            # Buscar leads sin asignar del rubro indicado
            leads_result = self.sonora_client.table("marketplace_leads") \
                .select("id") \
                .ilike("rubro", f"%{rubro}%") \
                .eq("estado", "nuevo") \
                .is_("asesor_asignado_id", "null") \
                .limit(cantidad) \
                .execute()
            
            if not leads_result.data:
                return {
                    "success": False,
                    "error": f"No hay leads disponibles (sin asignar) para el rubro '{rubro}'"
                }
            
            # Asignar leads al asesor
            lead_ids = [lead["id"] for lead in leads_result.data]
            for lid in lead_ids:
                self.sonora_client.table("marketplace_leads") \
                    .update({
                        "asesor_asignado_id": asesor_id,
                        "estado": "contactado"
                    }) \
                    .eq("id", lid) \
                    .execute()
            
            return {
                "success": True,
                "asignados": len(lead_ids),
                "asesor": asesor_full_name,
                "rubro": rubro,
                "mensaje": f"Se asignaron {len(lead_ids)} leads de '{rubro}' al asesor {asesor_full_name}."
            }
            
        except Exception as e:
            logger.error(f"Error asignando leads: {e}")
            return {"success": False, "error": str(e)}
