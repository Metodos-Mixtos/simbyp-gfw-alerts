import json
import os
import locale
from google.cloud import storage

def make_relative(path, base):
    if path and os.path.isabs(path):
        return os.path.relpath(path, base)
    return path

# Establecer formato numérico español
locale.setlocale(locale.LC_ALL, "es_ES.UTF-8")

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
    sentinel_results=None
):
    """
    Construye un JSON consolidado con alertas, clusters y mapas enriquecidos.
    Formatea los valores numéricos con coma decimal y punto de miles (estilo español),
    elimina el doble %, y omite valores vacíos (None).
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
    report_data = {
        "TRIMESTRE": trimestre,
        "ANIO": anio,
        "HEADER_IMG1": os.path.relpath(ruta_header_img1, base_folder),
        "HEADER_IMG2": os.path.relpath(ruta_header_img2, base_folder),
        "FOOTER_IMG": os.path.relpath(ruta_footer_img, base_folder),
        "MAPA_ALERTAS": os.path.relpath(ruta_mapa_alertas, base_folder),
        # GFW
        "GFW_NOMINAL": summary["gfw_integrated_alerts__confidence"].get("nominal", 0),
        "GFW_ALTO": summary["gfw_integrated_alerts__confidence"].get("high", 0),
        "GFW_MUY_ALTO": summary["gfw_integrated_alerts__confidence"].get("highest", 0),
        "GFW_TOTAL": summary["gfw_integrated_alerts__confidence"].get("total", 0),
        # GLAD Landsat
        "GLADL_NOMINAL": summary["umd_glad_landsat_alerts__confidence"].get("nominal", 0),
        "GLADL_ALTO": summary["umd_glad_landsat_alerts__confidence"].get("high", 0),
        "GLADL_NO_DET": summary["umd_glad_landsat_alerts__confidence"].get("not_detected", 0),
        "GLADL_TOTAL": summary["umd_glad_landsat_alerts__confidence"].get("total", 0),
        # GLAD Sentinel
        "GLADS_NOMINAL": summary["umd_glad_sentinel2_alerts__confidence"].get("nominal", 0),
        "GLADS_ALTO": summary["umd_glad_sentinel2_alerts__confidence"].get("high", 0),
        "GLADS_NO_DET": summary["umd_glad_sentinel2_alerts__confidence"].get("not_detected", 0),
        "GLADS_TOTAL": summary["umd_glad_sentinel2_alerts__confidence"].get("total", 0),
        # WUR RADD
        "RADD_NOMINAL": summary["wur_radd_alerts__confidence"].get("nominal", 0),
        "RADD_ALTO": summary["wur_radd_alerts__confidence"].get("high", 0),
        "RADD_NO_DET": summary["wur_radd_alerts__confidence"].get("not_detected", 0),
        "RADD_TOTAL": summary["wur_radd_alerts__confidence"].get("total", 0),
        "METODOLOGIA": """
        <section class="metodologia">
            <h2>Metodología</h2>
            <p>Este reporte presenta las alertas de deforestación provenientes de Global Forest Watch para Bogotá y 19 municipios aledaños. Asimismo, incluye una caracterización de las áreas rurales donde se localizan dichas alertas, apoyada en imágenes satelitales y fuentes externas.</p>
            <p>Las alertas integradas provienen de tres subsistemas: Sentinel-2, Landsat y Radar. Para más información, consulte la plataforma GFW.</p>
            <p>Para más información, consulte Global Forest Watch.</p>
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
            cluster_info["mapa_sentinel"] = os.path.relpath(map_path, base_folder)

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
