import json
from dotenv import load_dotenv
import os

from src.download_gfw_data import get_api_key, get_start_end_dates, extract_polygon_from_file, download_alerts, save_to_csv, csv_to_geodataframe, save_geodataframe_to_geojson, summarize_alert_confidences
from src.process_gfw_alerts import process_alerts, cluster_alerts_by_section, get_cluster_bboxes, create_cluster_maps, build_report_json, plot_alerts_interactive, plot_alerts_with_boundaries
from src.download_sentinel_images import authenticate_gee, download_clusters
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

#START_DATE = "2025-01-01"
#END_DATE = "2025-03-31"
TRIMESTRE = "I"
ANIO = "2025"
START_DATE, END_DATE = get_start_end_dates(TRIMESTRE, ANIO)

INPUTS_PATH = os.getenv("INPUTS_PATH")
POLYGON_PATH = os.path.join(INPUTS_PATH, "area_estudio/area_estudio_dissolved.geojson")
VEREDAS_PATH = os.path.join(INPUTS_PATH, "area_estudio/shp_CRVeredas_2024/shp_CRVeredas_2024.shp")
SECCIONES_PATH = os.path.join(INPUTS_PATH, "panel_secciones_rurales/V3/panel_SDP_29092025-v3.shp")
LOGO_PATH = os.path.join(INPUTS_PATH, "deforestation_reports/Logo_SDP.jpeg")

# Crear carpeta de salida con las fechas
fecha_rango = f"{START_DATE}_a_{END_DATE}"
OUTPUT_FOLDER = os.path.join(ONEDRIVE_PATH, "datos", "Alertas GFW", fecha_rango)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Generar nombres de archivos con fechas
csv_filename = f"alertas_gfw_{fecha_rango}.csv"
geojson_filename = f"alertas_gfw_{fecha_rango}.geojson"
map_filename = f"alertas_mapa_{fecha_rango}.html"
bbox_filename = f"bbox_area_{fecha_rango}.geojson"
summary_filename = f"alertas_resumen_{fecha_rango}.json"
df_analysis_filename = f"alertas_gfw_analisis_{fecha_rango}.geojson"

CSV_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, csv_filename)
GEOJSON_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, geojson_filename)
MAP_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, map_filename)
BBOX_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, bbox_filename)
SUMMARY_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, summary_filename)
DF_ANALYSIS_PATH = os.path.join(OUTPUT_FOLDER, df_analysis_filename)
SENTINEL_IMAGES_PATH = os.path.join(OUTPUT_FOLDER, "sentinel_imagenes")
JSON_FINAL_PATH = os.path.join(OUTPUT_FOLDER, "reporte_final.json")

TPL_PATH = Path("gfw_alerts/reporte/report_template.html")
DATA_PATH = Path(OUTPUT_FOLDER) / "reporte_final.json"
OUT_PATH  = Path(OUTPUT_FOLDER) / "reporte_final.html"

# === FLUJO PRINCIPAL ===
if __name__ == "__main__":
    print("🔐 Autenticando en GFW...")
    token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY3MDY5NzE5Y2EwOGIwM2VhMjAyOWM1YiIsInJvbGUiOiJVU0VSIiwicHJvdmlkZXIiOiJsb2NhbCIsImVtYWlsIjoiamF2aWVyZ3VlcnJhbTFAZ21haWwuY29tIiwiZXh0cmFVc2VyRGF0YSI6eyJhcHBzIjpbImdmdyJdfSwiY3JlYXRlZEF0IjoxNzUzMzg3ODEwODA3LCJpYXQiOjE3NTMzODc4MTB9.21cgPqRGAkFtdd6uQV6TDLP7Xq7s7Hj1WyHVeAnM70Y'

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
    alerts_with_clusters.to_file(os.path.join(OUTPUT_FOLDER, df_analysis_filename))
    clusters_bboxes = get_cluster_bboxes(alerts_with_clusters) #Obtener bboxes por cluster
    
    print("Descargando imágenes de Sentinel-2...")
    print("...Inicializando Google Earth Engine...")
    authenticate_gee()
    download_clusters(clusters_bboxes, START_DATE, END_DATE, SENTINEL_IMAGES_PATH) #Descargar imágenes Sentinel por cluster
    
    print("🖼️ Creando mapas enriquecidos para todos los clusters...")
    cluster_maps = create_cluster_maps(clusters_bboxes, alerts_with_clusters, SENTINEL_IMAGES_PATH, SENTINEL_IMAGES_PATH)

    #print("🗺️ Guardando visualización como imagen...")
    #plot_alerts_with_boundaries(gdf_alertas, POLYGON_PATH, MAP_OUTPUT_PATH, START_DATE, END_DATE)
    
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
        output_path=JSON_FINAL_PATH
    )
    
    print("📝 Renderizando reporte HTML...")
    render(TPL_PATH, DATA_PATH, OUT_PATH)

    print("✅ Proceso completo. Archivos guardados:")

