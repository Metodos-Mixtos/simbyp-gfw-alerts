import json
from dotenv import load_dotenv
import os

from src.download_gfw_data import get_api_key, extract_polygon_from_file, download_alerts, save_to_csv, csv_to_geodataframe, save_geodataframe_to_geojson, plot_alerts_with_boundaries, save_bbox_to_geojson, summarize_alert_confidences

# Load environment variables from .env file
load_dotenv("dot_env_content.env")

# === PARÁMETROS ===
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
ALIAS = os.getenv("ALIAS")
EMAIL = os.getenv("EMAIL")
ORG = os.getenv("ORG")
ONEDRIVE_PATH = os.getenv("ONEDRIVE_PATH")

START_DATE = "2025-01-01"
END_DATE = "2025-03-31"
INPUTS_PATH = os.getenv("INPUTS_PATH")
POLYGON_PATH = os.path.join(INPUTS_PATH, "area_estudio/area_estudio_dissolved.geojson")

# Crear carpeta de salida con las fechas
fecha_rango = f"{START_DATE}_to_{END_DATE}"
OUTPUT_FOLDER = os.path.join(ONEDRIVE_PATH, "datos", "Alertas GFW", fecha_rango)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Generar nombres de archivos con fechas
csv_filename = f"alertas_gfw_{fecha_rango}.csv"
geojson_filename = f"alertas_gfw_{fecha_rango}.geojson"
map_filename = f"alertas_map_{fecha_rango}.png"
bbox_filename = f"bbox_area_{fecha_rango}.geojson"
summary_filename = f"alert_summary_{fecha_rango}.json"

CSV_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, csv_filename)
GEOJSON_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, geojson_filename)
MAP_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, map_filename)
BBOX_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, bbox_filename)
SUMMARY_OUTPUT_PATH = os.path.join(OUTPUT_FOLDER, summary_filename)

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
    print(json.dumps(summary, indent=2))

    print("💾 Guardando resumen como JSON...")
    with open(SUMMARY_OUTPUT_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    print("🌍 Guardando GeoDataFrame como GeoJSON...")
    save_geodataframe_to_geojson(gdf_alertas, GEOJSON_OUTPUT_PATH)
    
    print("📦 Guardando bounding box como GeoJSON...")
    save_bbox_to_geojson(POLYGON_PATH, BBOX_OUTPUT_PATH)

    print("🗺️ Guardando visualización como imagen...")
    plot_alerts_with_boundaries(gdf_alertas, POLYGON_PATH, 
                                MAP_OUTPUT_PATH, START_DATE, END_DATE)

    print("✅ Proceso completo. Archivos guardados:")
    print(f" - CSV: {CSV_OUTPUT_PATH}")
    print(f" - GeoJSON: {GEOJSON_OUTPUT_PATH}")
    print(f" - Bounding Box: {BBOX_OUTPUT_PATH}")
    print(f" - Mapa PNG: {MAP_OUTPUT_PATH}")
