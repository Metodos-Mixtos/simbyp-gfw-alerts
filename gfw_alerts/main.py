from download_gfw_data import (
    authenticate_gfw,
    get_api_key,
    extract_polygon_from_file,
    download_alerts,
    save_to_csv,
    csv_to_geodataframe,
    save_geodataframe_to_geojson,
    plot_alerts_with_boundaries, 
    save_bbox_to_geojson, 
    summarize_alert_confidences
)

import json
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv('dot_env_content.txt')

# === PARÁMETROS ===
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
ALIAS = os.getenv("ALIAS")
EMAIL = os.getenv("EMAIL")
ORG = os.getenv("ORG")

START_DATE = os.getenv("START_DATE")
END_DATE = os.getenv("END_DATE")
POLYGON_PATH = os.getenv("POLYGON_PATH")
CSV_OUTPUT = os.getenv("CSV_OUTPUT")
GEOJSON_OUTPUT = os.getenv("GEOJSON_OUTPUT")
MAP_OUTPUT = os.getenv("MAP_OUTPUT")
BBOX_OUTPUT = os.getenv("BBOX_OUTPUT")
SUMMARY_OUTPUT = os.getenv("SUMMARY_OUTPUT")

# === FLUJO PRINCIPAL ===
if __name__ == "__main__":
    print("🔐 Autenticando en GFW...")
    token = authenticate_gfw(USERNAME, PASSWORD)

    print("🔑 Solicitando API key...")
    api_key = get_api_key(token, alias=ALIAS, email=EMAIL, organization=ORG)

    print("📦 Extrayendo polígono del archivo...")
    polygon = extract_polygon_from_file(POLYGON_PATH)

    print("⬇️ Descargando alertas...")
    data = download_alerts(api_key, START_DATE, END_DATE, polygon)

    print("💾 Guardando CSV...")
    save_to_csv(data, CSV_OUTPUT)

    print("📄 Convirtiendo CSV en GeoDataFrame...")
    gdf_alertas = csv_to_geodataframe(CSV_OUTPUT)
    
    print("📊 Resumiendo niveles de alerta...")
    summary = summarize_alert_confidences(gdf_alertas)
    print(json.dumps(summary, indent=2))

    print("💾 Guardando resumen como JSON...")
    with open(SUMMARY_OUTPUT, "w") as f:
        json.dump(summary, f, indent=2)

    print("🌍 Guardando GeoDataFrame como GeoJSON...")
    save_geodataframe_to_geojson(gdf_alertas, GEOJSON_OUTPUT)
    
    print("📦 Guardando bounding box como GeoJSON...")
    save_bbox_to_geojson(POLYGON_PATH, BBOX_OUTPUT)

    print("🗺️ Guardando visualización como imagen...")
    plot_alerts_with_boundaries(gdf_alertas, POLYGON_PATH, MAP_OUTPUT, START_DATE, END_DATE)

    print("✅ Proceso completo. Archivos guardados:")
    print(f" - CSV: {CSV_OUTPUT}")
    print(f" - GeoJSON: {GEOJSON_OUTPUT}")
    print(f" - Bounding Box: {BBOX_OUTPUT}")
    print(f" - Mapa PNG: {MAP_OUTPUT}")
