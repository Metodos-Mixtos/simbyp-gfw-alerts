import argparse
from dotenv import load_dotenv
import os
from pathlib import Path

# === Importar funciones del pipeline ===
from src.download_gfw_data import (
    get_api_key,
    get_start_end_dates,
    extract_polygon_from_file,
    download_alerts,
    save_to_csv,
    csv_to_geodataframe,
    save_geodataframe_to_geojson,
    summarize_alert_confidences,
    authenticate_gfw
)
from src.process_gfw_alerts import (
    process_alerts,
    cluster_alerts_by_section,
    get_cluster_bboxes,
)
from src.create_final_json import build_report_json
from src.maps import plot_alerts_interactive, plot_sentinel_cluster_interactive
from reporte.render_report import render

# === Cargar variables de entorno ===
load_dotenv("dot_env_content.env")

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
ALIAS = os.getenv("ALIAS")
EMAIL = os.getenv("EMAIL")
ORG = os.getenv("ORG")
ONEDRIVE_PATH = os.getenv("ONEDRIVE_PATH")
GOOGLE_CLOUD_PROJECT = os.getenv("GCP_PROJECT")
INPUTS_PATH = os.getenv("INPUTS_PATH")

# === Rutas de insumos ===
POLYGON_PATH = os.path.join(INPUTS_PATH, "area_estudio", "gfw", "area_estudio.geojson")
VEREDAS_PATH = os.path.join(INPUTS_PATH, "area_estudio", "gfw", "veredas_cund_2024/veredas_cund_2024.shp")
SECCIONES_PATH = os.path.join(INPUTS_PATH, "area_estudio", "gfw", "panel_secciones_rurales", "V3/panel_SDP_29092025-v3.shp")
LOGO_PATH = os.path.join(INPUTS_PATH, "Logo_SDP.jpeg")

if __name__ == "__main__":
    # === Argumentos de ejecución ===
    parser = argparse.ArgumentParser(description="Pipeline de alertas GFW")
    parser.add_argument("--trimestre", type=str, required=True, help="Trimestre: I, II, III o IV")
    parser.add_argument("--anio", type=str, required=True, help="Año en formato YYYY")
    args = parser.parse_args()

    TRIMESTRE = args.trimestre
    ANIO = args.anio
    START_DATE, END_DATE = get_start_end_dates(TRIMESTRE, ANIO)

    # === Carpetas de salida ===
    fecha_rango = f"{TRIMESTRE}_trim_{ANIO}"
    OUTPUT_FOLDER = os.path.join(ONEDRIVE_PATH, "outputs", fecha_rango)
    SENTINEL_IMAGES_PATH = os.path.join(OUTPUT_FOLDER, "sentinel_imagenes")
    os.makedirs(SENTINEL_IMAGES_PATH, exist_ok=True)

    # === Rutas de archivos ===
    CSV_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_gfw_{fecha_rango}.csv")
    GEOJSON_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_gfw_{fecha_rango}.geojson")
    DF_ANALYSIS_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_gfw_analisis_{fecha_rango}.geojson")
    MAP_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_mapa_{fecha_rango}.html")
    JSON_FINAL_PATH = os.path.join(OUTPUT_FOLDER, "reporte_final.json")
    TPL_PATH = Path("gfw_alerts/reporte/report_template.html")
    OUT_PATH = Path(OUTPUT_FOLDER) / "reporte_final.html"
    DATA_PATH = Path(JSON_FINAL_PATH)

    # === Autenticación ===
    print("🔐 Autenticando en GFW...")
    token = authenticate_gfw(username=USERNAME, password=PASSWORD)
    api_key = get_api_key(token, alias=ALIAS, email=EMAIL, organization=ORG)

    # === Descarga y procesamiento de alertas ===
    print("📦 Extrayendo polígono del archivo...")
    polygon = extract_polygon_from_file(POLYGON_PATH)

    print("⬇️ Descargando alertas...")
    data = download_alerts(api_key, START_DATE, END_DATE, polygon)
    save_to_csv(data, CSV_OUTPUT_PATH)

    print("📄 Convirtiendo CSV a GeoDataFrame...")
    gdf_alertas = csv_to_geodataframe(CSV_OUTPUT_PATH)
    save_geodataframe_to_geojson(gdf_alertas, GEOJSON_OUTPUT_PATH)

    print("📊 Resumiendo niveles de alerta...")
    summary = summarize_alert_confidences(gdf_alertas)

    print("🔍 Enriqueciendo alertas con información territorial...")
    alerts_gdf = process_alerts(GEOJSON_OUTPUT_PATH, VEREDAS_PATH, SECCIONES_PATH)
    alerts_with_clusters = cluster_alerts_by_section(alerts_gdf)
    alerts_with_clusters.to_file(DF_ANALYSIS_PATH)
    clusters_bboxes = get_cluster_bboxes(alerts_with_clusters)

    # === Crear mapas Sentinel interactivos ===
    print("🛰️ Generando mapas Sentinel-2 interactivos...")
    sentinel_results = []
    for _, row in clusters_bboxes.iterrows():
        cluster_id = int(row["cluster_id"])
        output_path = os.path.join(SENTINEL_IMAGES_PATH, f"sentinel_cluster_{cluster_id}.html")

        map_path = plot_sentinel_cluster_interactive(
            cluster_geom=row.geometry,
            cluster_id=cluster_id,
            start_date=START_DATE,
            end_date=END_DATE,
            output_path=output_path, 
            alerts_gdf=gdf_alertas,
            project=GOOGLE_CLOUD_PROJECT
        )

        if map_path:
            sentinel_results.append({
                "cluster_id": cluster_id,
                "map_html": map_path
            })

    # === Crear mapa general de alertas ===
    print("🗺️ Creando visualización general...")
    plot_alerts_interactive(gdf_alertas, POLYGON_PATH, MAP_OUTPUT_PATH)

    # === Construir JSON consolidado ===
    print("📝 Construyendo JSON final...")
    report_data = build_report_json(
        summary,
        alerts_with_clusters,
        trimestre=TRIMESTRE,
        anio=ANIO,
        ruta_logo=LOGO_PATH,
        ruta_mapa_alertas=MAP_OUTPUT_PATH,
        output_path=JSON_FINAL_PATH,
        sentinel_results=sentinel_results
    )

    # === Renderizar reporte HTML ===
    print("📝 Renderizando reporte HTML...")
    render(TPL_PATH, DATA_PATH, OUT_PATH)

    print("✅ Proceso completo. Archivos guardados en:")
    print(f"   - JSON: {JSON_FINAL_PATH}")
    print(f"   - HTML: {OUT_PATH}")
