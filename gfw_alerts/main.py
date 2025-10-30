import argparse
from dotenv import load_dotenv
import os

from src.download_gfw_data import get_api_key, get_start_end_dates, extract_polygon_from_file, download_alerts, save_to_csv, csv_to_geodataframe, save_geodataframe_to_geojson, summarize_alert_confidences, authenticate_gfw
from src.process_gfw_alerts import process_alerts, cluster_alerts_by_section, get_cluster_bboxes, create_cluster_maps, plot_alerts_interactive
from src.download_sentinel_images import authenticate_gee, download_sentinel_rgb_for_region
from src.create_final_json import build_report_json
from reporte.render_report import render
from pathlib import Path


# Load environment variables from .env file
load_dotenv("dot_env_content.env")

# === PARÁMETROS ===
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
ALIAS = os.getenv("ALIAS")
EMAIL = os.getenv("EMAIL")
ORG = os.getenv("ORG")
ONEDRIVE_PATH = os.getenv("ONEDRIVE_PATH")
GOOGLE_CLOUD_PROJECT = os.getenv("GCP_PROJECT")

#TRIMESTRE = "I"
#ANIO = "2025"
#START_DATE, END_DATE = get_start_end_dates(TRIMESTRE, ANIO)

# Definir rutas de los insumos
INPUTS_PATH = os.getenv("INPUTS_PATH")
POLYGON_PATH = os.path.join(INPUTS_PATH, "gfw/area_estudio/area_estudio.geojson")
VEREDAS_PATH = os.path.join(INPUTS_PATH, "gfw/area_estudio/veredas_cund_2024/veredas_cund_2024.shp")
SECCIONES_PATH = os.path.join(INPUTS_PATH, "gfw/panel_secciones_rurales/V3/panel_SDP_29092025-v3.shp")
LOGO_PATH = os.path.join(INPUTS_PATH, "gfw/Logo_SDP.jpeg")

# === FLUJO PRINCIPAL ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de alertas GFW")
    parser.add_argument("--trimestre", type=str, required=True, help="Trimestre: I, II, III o IV")
    parser.add_argument("--anio", type=str, required=True, help="Año en formato YYYY")
    args = parser.parse_args()

    TRIMESTRE = args.trimestre
    ANIO = args.anio
    START_DATE, END_DATE = get_start_end_dates(TRIMESTRE, ANIO)
    
    # Crear carpeta de salida con las fechas
    fecha_rango = f"{TRIMESTRE}_trim_{ANIO}"
    OUTPUT_FOLDER = os.path.join(ONEDRIVE_PATH, "outputs", fecha_rango)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Generar nombres de archivos con fechas
    CSV_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_gfw_{fecha_rango}.csv")
    GEOJSON_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_gfw_{fecha_rango}.geojson")
    MAP_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_mapa_{fecha_rango}.html")
    BBOX_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"bbox_area_{fecha_rango}.geojson")
    SUMMARY_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_resumen_{fecha_rango}.json")
    DF_ANALYSIS_PATH = os.path.join(OUTPUT_FOLDER, f"alertas_gfw_analisis_{fecha_rango}.geojson")
    SENTINEL_IMAGES_PATH = os.path.join(OUTPUT_FOLDER, "sentinel_imagenes")
    JSON_FINAL_PATH = os.path.join(OUTPUT_FOLDER, "reporte_final.json")

    # Definir rutas para la creación del reporte HTML
    TPL_PATH = Path("gfw_alerts/reporte/report_template.html")
    DATA_PATH = Path(OUTPUT_FOLDER) / "reporte_final.json"
    OUT_PATH  = Path(OUTPUT_FOLDER) / "reporte_final.html"
    
    print("🔐 Autenticando en GFW...")
    token = authenticate_gfw(username=USERNAME, password=PASSWORD)
    #token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY3MDY5NzE5Y2EwOGIwM2VhMjAyOWM1YiIsInJvbGUiOiJVU0VSIiwicHJvdmlkZXIiOiJsb2NhbCIsImVtYWlsIjoiamF2aWVyZ3VlcnJhbTFAZ21haWwuY29tIiwiZXh0cmFVc2VyRGF0YSI6eyJhcHBzIjpbImdmdyJdfSwiY3JlYXRlZEF0IjoxNzUzMzg3ODEwODA3LCJpYXQiOjE3NTMzODc4MTB9.21cgPqRGAkFtdd6uQV6TDLP7Xq7s7Hj1WyHVeAnM70Y'

    print("🔑 Solicitando API key...")
    api_key = get_api_key(token, alias=ALIAS, email=EMAIL, organization=ORG)

    print("📦 Extrayendo polígono del archivo...")
    polygon = extract_polygon_from_file(POLYGON_PATH)

    print("⬇️ Descargando alertas...")
    data = download_alerts(api_key, START_DATE, END_DATE, polygon)

    print("💾 Guardando CSV...")
    save_to_csv(data, CSV_OUTPUT_PATH)

    print("📄 Convirtiendo CSV en GeoDataFrame...")
    gdf_alertas = csv_to_geodataframe(CSV_OUTPUT_PATH)
    
    print("📊 Resumiendo niveles de alerta...")
    summary = summarize_alert_confidences(gdf_alertas)

    print("🌍 Guardando GeoDataFrame como GeoJSON...")
    save_geodataframe_to_geojson(gdf_alertas, GEOJSON_OUTPUT_PATH)
    
    print("Caracterizando alertas con información del panel...")
    alerts_gdf = process_alerts(GEOJSON_OUTPUT_PATH, VEREDAS_PATH, SECCIONES_PATH) #Procesar alertas
    alerts_with_clusters = cluster_alerts_by_section(alerts_gdf) #Crear clusters
    alerts_with_clusters.to_file(DF_ANALYSIS_PATH)
    clusters_bboxes = get_cluster_bboxes(alerts_with_clusters) #Obtener bboxes por cluster
    
    print("⬇️ Descargando imágenes de Sentinel-2...")
    authenticate_gee(project=GOOGLE_CLOUD_PROJECT)
    
    sentinel_results = []
    for _, row in clusters_bboxes.iterrows():
        cluster_id = int(row["cluster_id"])
        output_path = os.path.join(SENTINEL_IMAGES_PATH, f"sentinel_cluster_{cluster_id}.tif")

        obs = download_sentinel_rgb_for_region(
            row.geometry, START_DATE, END_DATE, output_path)

        sentinel_results.append({
            "cluster_id": cluster_id,
            "obs": obs if obs else None
        })
    
    print("🖼️ Creando mapas enriquecidos para todos los clusters...")
    cluster_maps = create_cluster_maps(clusters_bboxes, alerts_with_clusters, SENTINEL_IMAGES_PATH, SENTINEL_IMAGES_PATH)
    
    print("🗺️ Guardando visualización interactiva...")
    plot_alerts_interactive(gdf_alertas, POLYGON_PATH, MAP_OUTPUT_PATH)
    
    print("📝 Construyendo JSON final...")
    
    report_data = build_report_json(
        summary,
        alerts_with_clusters,
        cluster_maps,
        trimestre=TRIMESTRE,
        anio=ANIO,
        ruta_logo=LOGO_PATH, 
        ruta_mapa_alertas = MAP_OUTPUT_PATH,
        output_path=JSON_FINAL_PATH, 
        sentinel_results=sentinel_results
    )
    
    print("📝 Renderizando reporte HTML...")
    render(TPL_PATH, DATA_PATH, OUT_PATH)

    print("✅ Proceso completo. Archivos guardados:")

