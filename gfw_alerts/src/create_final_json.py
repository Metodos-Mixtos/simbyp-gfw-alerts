import json
import os
import locale
from google.cloud import storage
from datetime import datetime

def make_relative(path, base):
    """
    Convierte una ruta a relativa respecto a base.
    Si la ruta es GCS (gs://...), la devuelve tal cual.
    Normaliza rutas para asegurar que sean relativas a la carpeta base.
    SIEMPRE usa forward slashes (/) para compatibilidad web.
    """
    if not path:
        return path
    if isinstance(path, str) and path.startswith("gs://"):
        return path  # Rutas GCS se mantienen absolutas
    
    # Normalizar ambas rutas (convertir \ a / y resolver ..)
    path_norm = os.path.normpath(path).replace("\\", "/")
    base_norm = os.path.normpath(base).replace("\\", "/")
    
    # Si la ruta está dentro de base, calcular ruta relativa
    if path_norm.startswith(base_norm):
        # Remover el prefijo de base y el separador
        relative = path_norm[len(base_norm):].lstrip("/")
        return relative
    
    # Si no está dentro de base, usar relpath y normalizar
    if os.path.isabs(path):
        result = os.path.relpath(path, base).replace("\\", "/")
        return result
    
    # Para rutas ya relativas, solo normalizar separadores
    return path.replace("\\", "/")

# Establecer formato numérico español
locale.setlocale(locale.LC_ALL, "es_ES.UTF-8")

def format_date_spanish(date_str):
    """Convierte fecha YYYY-MM-DD a formato DD/MM/YYYY"""
    if not date_str:
        return ""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%d/%m/%Y")
    except:
        return date_str

def build_report_json(
    summary,
    alerts_with_clusters,
    trimestre,
    anio,
    ruta_header_img1,
    ruta_header_img2,
    ruta_footer_img,
    ruta_mapa_alertas,
    output_path,
    sentinel_results=None,
    start_date=None,
    end_date=None,
    es_semanal=False
):
    """
    Construye un JSON consolidado con alertas, clusters y mapas enriquecidos.
    Formatea los valores numéricos con coma decimal y punto de miles (estilo español),
    elimina el doble %, y omite valores vacíos (None).
    
    Parámetros adicionales para reportes semanales:
    - start_date: fecha de inicio del reporte semanal (formato YYYY-MM-DD)
    - end_date: fecha de fin del reporte semanal (formato YYYY-MM-DD)
    - es_semanal: True si es reporte semanal, False si es trimestral
    """
    base_folder = os.path.dirname(output_path)

    # === Función auxiliar para formatear números ===
    def fmt(value):
        """
        Formatea números con coma decimal y punto de miles.
        Si el valor no es numérico o es NaN, devuelve None.
        """
        if value is None:
            return None
        try:
            if isinstance(value, (float, int)):
                val = round(float(value), 1)
                formatted = f"{val:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
                return formatted
            else:
                return None
        except Exception:
            return None

    # === Base del reporte ===
    # Preparar textos según el tipo de reporte
    if es_semanal:
        fecha_inicio_fmt = format_date_spanish(start_date)
        fecha_fin_fmt = format_date_spanish(end_date)
        titulo_reporte = "Reporte semanal de alertas de deforestación y cambios en el páramo"
        periodo_texto = f"Semana del {fecha_inicio_fmt} al {fecha_fin_fmt}"
        titulo_mapa = f"Alertas de deforestación - Semana del {fecha_inicio_fmt} al {fecha_fin_fmt}"
    else:
        titulo_reporte = "Reporte trimestral de alertas de deforestación y cambios en el páramo"
        periodo_texto = f"{trimestre} trimestre de {anio}"
        titulo_mapa = f"Alertas de deforestación en el {trimestre} trimestre de {anio}"
    
    # Determinar si hay alertas de muy alto nivel
    gfw_conf = summary.get("gfw_integrated_alerts__confidence", {})
    gladl_conf = summary.get("umd_glad_landsat_alerts__confidence", {})
    glads_conf = summary.get("umd_glad_sentinel2_alerts__confidence", {})
    radd_conf = summary.get("wur_radd_alerts__confidence", {})
    hay_alertas_muy_alto = gfw_conf.get("highest", 0) > 0
    seccion_muy_alto_titulo = "<h3>Alertas de nivel muy alto</h3>" if hay_alertas_muy_alto else ""
    
    # Array auxiliar para mostrar mapa solo una vez (workaround para sistema de templates)
    mostrar_mapa = [True] if hay_alertas_muy_alto else []
    
    report_data = {
        "TRIMESTRE": trimestre if not es_semanal else None,
        "ANIO": anio if not es_semanal else None,
        "ES_SEMANAL": es_semanal,
        "FECHA_INICIO": start_date if es_semanal else None,
        "FECHA_FIN": end_date if es_semanal else None,
        "TITULO_REPORTE": titulo_reporte,
        "PERIODO_TEXTO": periodo_texto,
        "TITULO_MAPA": titulo_mapa,
        "SECCION_MUY_ALTO_TITULO": seccion_muy_alto_titulo,
        "MOSTRAR_MAPA": mostrar_mapa,
        "HEADER_IMG1": make_relative(ruta_header_img1, base_folder),
        "HEADER_IMG2": make_relative(ruta_header_img2, base_folder),
        "FOOTER_IMG": make_relative(ruta_footer_img, base_folder),
        "MAPA_ALERTAS": make_relative(ruta_mapa_alertas, base_folder),
        # GFW
        "GFW_NOMINAL": gfw_conf.get("nominal", 0),
        "GFW_ALTO": gfw_conf.get("high", 0),
        "GFW_MUY_ALTO": gfw_conf.get("highest", 0),
        "GFW_TOTAL": gfw_conf.get("total", 0),
        # GLAD Landsat
        "GLADL_NOMINAL": gladl_conf.get("nominal", 0),
        "GLADL_ALTO": gladl_conf.get("high", 0),
        "GLADL_NO_DET": gladl_conf.get("not_detected", 0),
        "GLADL_TOTAL": gladl_conf.get("total", 0),
        # GLAD Sentinel
        "GLADS_NOMINAL": glads_conf.get("nominal", 0),
        "GLADS_ALTO": glads_conf.get("high", 0),
        "GLADS_NO_DET": glads_conf.get("not_detected", 0),
        "GLADS_TOTAL": glads_conf.get("total", 0),
        # WUR RADD
        "RADD_NOMINAL": radd_conf.get("nominal", 0),
        "RADD_ALTO": radd_conf.get("high", 0),
        "RADD_NO_DET": radd_conf.get("not_detected", 0),
        "RADD_TOTAL": radd_conf.get("total", 0),
        "METODOLOGIA": """
        <section class="metodologia">
            <h2>Metodología</h2>
            <p>Este reporte presenta las alertas de deforestación provenientes de Global Forest Watch para Bogotá y 19 municipios aledaños. Asimismo, incluye una caracterización de las áreas rurales donde se localizan dichas alertas, apoyada en imágenes satelitales y fuentes externas.</p>
            <p>Las alertas se generan a partir de la comparación de imágenes satelitales de diferentes fechas, identificando áreas donde ha ocurrido una pérdida de cobertura arbórea.
            <p>Para más detalles sobre la metodología, visite la sección de <a href="https://www.globalforestwatch.org/blog/es/data-and-tools/alertas-de-deforestacion-integradas/">Metodología de GFW</a>.</p>
        </section>
        """,
        "SECCIONES_MUY_ALTO": []
    }

    # === Relación entre clusters y observaciones ===
    obs_lookup = {}
    map_lookup = {}
    if sentinel_results:
        obs_lookup = {res["cluster_id"]: res.get("obs", None) for res in sentinel_results}
        map_lookup = {res["cluster_id"]: res["map_html"] for res in sentinel_results}

    # === Construir secciones ===
    for _, row in alerts_with_clusters.drop_duplicates("cluster_id").iterrows():
        cid = int(row["cluster_id"])
        centroid = row.geometry.centroid

        cluster_info = {
            "cluster_id": cid,
            "municipio": row.get("NOMB_MPIO", ""),
            "vereda": row.get("NOMBRE_VER", ""),
            "densidad_poblacional": fmt(row.get("pobdens20")),
            "pib_m2": fmt(row.get("gdp_20_m2p")),
            "mercado_acceso": fmt(row.get("acss_mrkt")),
            "elevacion": fmt(row.get("elevation")),
            "ind_priv": fmt(row.get("dprivt")),
            "energia_pct": fmt(row.get("ENRG_PERC")),
            "acueducto_pct": fmt(row.get("ACUED_PERC")),
            "alcantarillado_pct": fmt(row.get("ALCLT_PERC")),
            "gas_pct": fmt(row.get("GAS_PERC")),
            "basura_pct": fmt(row.get("BASUR_PERC")),
            "internet_pct": fmt(row.get("INTER_PERC")),
            "lat": round(centroid.y, 6),
            "lon": round(centroid.x, 6),
        }

        obs = obs_lookup.get(cid)
        if obs:
            cluster_info["OBSERVACION_IMAGEN"] = [obs]

        map_path = map_lookup.get(cid)
        if map_path:
            cluster_info["mapa_sentinel"] = make_relative(map_path, base_folder)

        report_data["SECCIONES_MUY_ALTO"].append(cluster_info)

    # === Guardar JSON ===
    # If output_path is a GCS URI (gs://bucket/path/to/file.json) upload to the bucket,
    # otherwise save locally as before.
    if isinstance(output_path, str) and output_path.startswith("gs://"):
        # prepare JSON string (preserve utf-8)
        json_str = json.dumps(report_data, indent=2, ensure_ascii=False)

        # parse bucket and blob path
        _prefix, rest = output_path.split("gs://", 1)
        parts = rest.split("/", 1)
        bucket_name = parts[0]
        blob_path = parts[1] if len(parts) > 1 else ""

        # upload using google-cloud-storage client (uses GOOGLE_APPLICATION_CREDENTIALS)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        blob.upload_from_string(json_str.encode("utf-8"), content_type="application/json")
        print(f"✅ JSON final subido a: {output_path}")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON final guardado en: {output_path}")

    return report_data
