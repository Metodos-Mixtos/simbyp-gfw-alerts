import json
import os

def make_relative(path, base):
    if path and os.path.isabs(path):
        return os.path.relpath(path, base)
    return path

def build_report_json(summary, alerts_with_clusters, cluster_maps, trimestre, anio, ruta_logo, ruta_mapa_alertas, output_path, sentinel_results=None):
    """
    Construye un JSON consolidado con alertas, clusters y mapas enriquecidos.
    """
    base_folder = os.path.dirname(output_path)  
    # Base inicial
    report_data = {
        "TRIMESTRE": trimestre,
        "ANIO": anio,
        "LOGO": make_relative(ruta_logo, base_folder),
        "MAPA_ALERTAS": make_relative(ruta_mapa_alertas, base_folder),
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

        # GLAD Sentinel-2
        "GLADS_NOMINAL": summary["umd_glad_sentinel2_alerts__confidence"].get("nominal", 0),
        "GLADS_ALTO": summary["umd_glad_sentinel2_alerts__confidence"].get("high", 0),
        "GLADS_NO_DET": summary["umd_glad_sentinel2_alerts__confidence"].get("not_detected", 0),
        "GLADS_TOTAL": summary["umd_glad_sentinel2_alerts__confidence"].get("total", 0),

        # WUR RADD
        "RADD_NOMINAL": summary["wur_radd_alerts__confidence"].get("nominal", 0),
        "RADD_ALTO": summary["wur_radd_alerts__confidence"].get("high", 0),
        "RADD_NO_DET": summary["wur_radd_alerts__confidence"].get("not_detected", 0),
        "RADD_TOTAL": summary["wur_radd_alerts__confidence"].get("total", 0),
        "SECCIONES_MUY_ALTO": []
    }
    obs_lookup = {}
    if sentinel_results:
        obs_lookup = {res["cluster_id"]: res["obs"] for res in sentinel_results}

    # Loop de clusters
    for _, row in alerts_with_clusters.drop_duplicates("cluster_id").iterrows():
        cid = row["cluster_id"]

        # Buscar el mapa asociado
        map_path = next((m["map_path"] for m in cluster_maps if m["cluster_id"] == cid), None)
        
        obs = obs_lookup.get(cid, None)
        
        geom = row.geometry
        centroid = geom.centroid

        cluster_info = {
            "cluster_id": int(cid),
            "municipio": row.get("NOMB_MPIO", ""),
            "vereda": row.get("NOMBRE_VER", ""),
            "densidad_poblacional": row.get("pobdens20", None),
            "pib_m2": row.get("gdp_20_m2p", None),
            "mercado_acceso": row.get("acss_mrkt", None),
            "elevacion": row.get("elevation", None),
            "ind_priv": row.get("dprivt", None),
            "cobertura_arboles": row.get("treecv_24", None),
            "energia_pct": row.get("ENRG_PERC", None),
            "acueducto_pct": row.get("ACUED_PERC", None),
            "alcantarillado_pct": row.get("ALCLT_PERC", None),
            "gas_pct": row.get("GAS_PERC", None),
            "basura_pct": row.get("BASUR_PERC", None),
            "internet_pct": row.get("INTER_PERC", None),
            "mapa_cluster": make_relative(map_path, base_folder),    
            "lat": centroid.y,
            "lon": centroid.x,
            "OBSERVACION_IMAGEN": [obs] if obs else []
        }

        report_data["SECCIONES_MUY_ALTO"].append(cluster_info)

    # Guardar JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"✅ JSON final guardado en: {output_path}")
    return report_data