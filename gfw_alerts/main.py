import argparse
from dotenv import load_dotenv
import os
from pathlib import Path
import dotenv
import warnings
import pandas as pd
import geopandas as gpd

# Suppress urllib3 SSL warning
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

dotenv.load_dotenv()

# Authenticate with Google Cloud
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# === Importar funciones del pipeline ===
from src.download_gfw_data import (
    get_api_key,
    get_start_end_dates,
    get_weekly_dates,
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

# Cargar variables de entorno 
# Buscar el .env en la raíz del proyecto (un nivel arriba de bosques-bog)
env_path = Path(__file__).parent.parent / ".env"
print(f"Debug: env_path = {env_path}")
print(f"Debug: env_path exists = {env_path.exists()}")
load_dotenv(env_path)

USERNAME = os.getenv("GFW_USERNAME")
PASSWORD = os.getenv("GFW_PASSWORD")
ALIAS = os.getenv("ALIAS")
EMAIL = os.getenv("EMAIL")
ORG = os.getenv("ORG")
OUTPUTS_BASE_PATH = os.getenv("OUTPUTS_BASE_PATH")
GOOGLE_CLOUD_PROJECT = os.getenv("GCP_PROJECT")
INPUTS_PATH = os.getenv("INPUTS_PATH")

print(f"Debug: USERNAME = {USERNAME}")
print(f"Debug: PASSWORD = {'*' * len(PASSWORD) if PASSWORD else None}")
print(f"Debug: ALIAS = {ALIAS}")
print(f"Debug: EMAIL = {EMAIL}")
print(f"Debug: ORG = {ORG}")
print(f"Debug: OUTPUTS_BASE_PATH = {OUTPUTS_BASE_PATH}")
print(f"Debug: GOOGLE_CLOUD_PROJECT = {GOOGLE_CLOUD_PROJECT}")
print(f"Debug: INPUTS_PATH = {INPUTS_PATH}")

# === Validar que las variables de entorno se cargaron correctamente ===
required_env_vars = {
    "USERNAME": USERNAME,
    "PASSWORD": PASSWORD,
    "ALIAS": ALIAS,
    "EMAIL": EMAIL,
    "ORG": ORG,
    "OUTPUTS_BASE_PATH": OUTPUTS_BASE_PATH,
    "GCP_PROJECT": GOOGLE_CLOUD_PROJECT,
    "INPUTS_PATH": INPUTS_PATH,
}

missing_vars = [key for key, value in required_env_vars.items() if value is None]

if missing_vars:
    print(f"Error: Faltan las siguientes variables de entorno en {env_path}:")
    for var in missing_vars:
        print(f" - {var}")
    exit(1)

# === Rutas de insumos ===
POLYGON_PATH = os.path.join(INPUTS_PATH, "area_estudio", "gfw", "area_estudio.geojson")
VEREDAS_PATH = os.path.join(INPUTS_PATH, "area_estudio", "gfw", "veredas_cund_2024/veredas_cund_2024.shp")
SECCIONES_PATH = os.path.join(INPUTS_PATH, "area_estudio", "gfw", "panel_secciones_rurales", "V3/panel_SDP_29092025-v3.shp")
HEADER_IMG1_PATH = os.path.join(INPUTS_PATH, "area_estudio", "asi_4.png")
HEADER_IMG2_PATH = os.path.join(INPUTS_PATH, "area_estudio", "bogota_4.png")
FOOTER_IMG_PATH = os.path.join(INPUTS_PATH, "area_estudio", "secre_5.png")

if __name__ == "__main__":
    # === Argumentos de ejecución ===
    parser = argparse.ArgumentParser(description="Pipeline de alertas GFW")
    parser.add_argument("--trimestre", type=str, required=False, help="Trimestre: I, II, III o IV (opcional, si se omite genera reporte semanal)")
    parser.add_argument("--anio", type=str, required=False, help="Año en formato YYYY (opcional, requerido si se especifica trimestre)")
    args = parser.parse_args()

    # Determinar si es reporte semanal o trimestral
    if args.trimestre and args.anio:
        # Modo trimestral
        TRIMESTRE = args.trimestre
        ANIO = args.anio
        START_DATE, END_DATE = get_start_end_dates(TRIMESTRE, ANIO)
        es_reporte_semanal = False
        print(f"📅 Generando reporte TRIMESTRAL: {TRIMESTRE} trimestre {ANIO}")
        print(f"   Rango de fechas: {START_DATE} a {END_DATE}")
    elif args.trimestre or args.anio:
        # Error: se especificó solo uno de los parámetros
        print("Error: Debes especificar tanto --trimestre como --anio, o ninguno de los dos para reporte semanal.")
        exit(1)
    else:
        # Modo semanal (sin parámetros)
        START_DATE, END_DATE = get_weekly_dates()
        TRIMESTRE = None
        ANIO = None
        es_reporte_semanal = True
        print(f"📅 Generando reporte SEMANAL")
        print(f"   Rango de fechas: {START_DATE} a {END_DATE}")

    # === Carpetas de salida (local para procesamiento) ===
    if es_reporte_semanal:
        # Para reportes semanales, usar el rango de fechas
        fecha_rango = f"semana_{START_DATE}_a_{END_DATE}"
    else:
        # Para reportes trimestrales, usar el formato anterior
        fecha_rango = f"{TRIMESTRE}_trim_{ANIO}"
    
    OUTPUT_FOLDER = os.path.join("temp_data", fecha_rango)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    SENTINEL_IMAGES_PATH = os.path.join(OUTPUT_FOLDER, "sentinel_imagenes")
    os.makedirs(SENTINEL_IMAGES_PATH, exist_ok=True)

    # === Descargar imágenes de encabezado y pie de página desde GCS ===
    from google.cloud import storage

    def download_gcs_to_local(gcs_path, local_path):
        _, rest = gcs_path.split("gs://", 1)
        bucket_name, blob_path = rest.split("/", 1)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.download_to_filename(local_path)

    local_header1 = os.path.join(OUTPUT_FOLDER, "asi_4.png")
    download_gcs_to_local(HEADER_IMG1_PATH, local_header1)
    local_header2 = os.path.join(OUTPUT_FOLDER, "bogota_4.png")
    download_gcs_to_local(HEADER_IMG2_PATH, local_header2)
    local_footer = os.path.join(OUTPUT_FOLDER, "secre_5.png")
    download_gcs_to_local(FOOTER_IMG_PATH, local_footer)

    # === Rutas de archivos (locales) ===
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
    
    # Check if there are any 'highest' confidence alerts
    if alerts_gdf.empty:
        print("⚠️  No se encontraron alertas de confianza 'highest' en el período seleccionado.")
        print("    El reporte se generará solo con estadísticas generales (sin clusters ni mapas Sentinel).")
        # Create empty structures for consistency
        alerts_with_clusters = alerts_gdf.copy()
        alerts_with_clusters['cluster_id'] = pd.Series(dtype='int64')
        clusters_bboxes = gpd.GeoDataFrame(columns=['cluster_id', 'geometry'], crs='EPSG:4326')
        sentinel_results = []
    else:
        alerts_with_clusters = cluster_alerts_by_section(alerts_gdf)
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

            if map_path and os.path.exists(output_path):
                print(f"✅ Mapa generado para cluster {cluster_id}: {output_path}")
                sentinel_results.append({
                    "cluster_id": cluster_id,
                    "map_html": map_path
                })
            else:
                print(f"❌ Mapa NO generado para cluster {cluster_id}: {output_path} (map_path: {map_path})")
    
    # Save analysis file (may be empty)
    alerts_with_clusters.to_file(DF_ANALYSIS_PATH)

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
        ruta_header_img1=local_header1,
        ruta_header_img2=local_header2,
        ruta_footer_img=local_footer,
        ruta_mapa_alertas=MAP_OUTPUT_PATH,
        output_path=JSON_FINAL_PATH,
        sentinel_results=sentinel_results,
        start_date=START_DATE if es_reporte_semanal else None,
        end_date=END_DATE if es_reporte_semanal else None,
        es_semanal=es_reporte_semanal
    )

    # === Renderizar reporte HTML ===
    print("📝 Renderizando reporte HTML...")
    render(TPL_PATH, DATA_PATH, OUT_PATH)

    # === Subir carpeta completa a GCS ===
    def upload_folder_to_gcs(local_folder, gcs_bucket, gcs_prefix):
        client = storage.Client()
        bucket = client.bucket(gcs_bucket)
        for root, dirs, files in os.walk(local_folder):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_folder)
                gcs_path = os.path.join(gcs_prefix, relative_path).replace("\\", "/")
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(local_path)
                print(f"✅ Subido {local_path} a gs://{gcs_bucket}/{gcs_path}")

    print("☁️ Subiendo outputs a GCS...")
    upload_folder_to_gcs(OUTPUT_FOLDER, "reportes-simbyp", f"reportes_gfw/{fecha_rango}")

    print("✅ Proceso completo. Archivos guardados en:")
    print(f"   - GCS: gs://reportes-simbyp/reportes_gfw/{fecha_rango}/")
