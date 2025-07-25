import requests
import json
from typing import List, Dict
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
import matplotlib.pyplot as plt
import contextily as ctx


ALERT_COLUMNS = [
    "gfw_integrated_alerts__confidence",
    "umd_glad_landsat_alerts__confidence",
    "umd_glad_sentinel2_alerts__confidence",
    "wur_radd_alerts__confidence"
]

def authenticate_gfw(username: str, password: str) -> str:
    """
    Autentica en la API de Global Forest Watch (GFW).

    Parámetros:
    - username (str): Dirección de correo electrónico registrada en GFW.
    - password (str): Contraseña correspondiente a ese usuario.

    Retorna:
    - str: Token Bearer para autenticación en solicitudes posteriores.
    """
    url = "https://data-api.globalforestwatch.org/auth/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {"username": username, "password": password}

    
    response = requests.post(url, headers=headers, data=payload)
    print(response.status_code)
    response.raise_for_status()
    return response.json()['data']['access_token']


def get_api_key(token: str, alias: str, email: str, organization: str = "") -> str:
    """
    Solicita una API key personalizada desde GFW usando un token Bearer válido.

    Parámetros:
    - token (str): Token Bearer obtenido por `authenticate_gfw()`.
    - alias (str): Nombre identificador para esta API key (ej. "api-key-proyectoX").
    - email (str): Correo electrónico del solicitante (visible en el panel de GFW).
    - organization (str, opcional): Organización o entidad que solicita la clave.

    Retorna:
    - str: API key para uso en endpoints protegidos.
    """
    url = "https://data-api.globalforestwatch.org/auth/apikey"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "alias": alias,
        "email": email,
        "organization": organization,
        "domains": []
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    #response.raise_for_status()
    return response.json().get("key")


def extract_polygon_from_file(filepath: str) -> List[List[float]]:
    """
    Extrae las coordenadas de un polígono desde un archivo GeoJSON o Shapefile.

    Parámetros:
    - filepath (str): Ruta al archivo .geojson o .shp.

    Retorna:
    - List[List[float]]: Lista de coordenadas [[lon, lat], ...] del primer polígono encontrado.
      Se asume que el archivo contiene al menos un polígono y está en EPSG:4326.
    """
    gdf = gpd.read_file(filepath)
    polygon = gdf.geometry.iloc[0]
    if polygon.geom_type == 'MultiPolygon':
        polygon = list(polygon.geoms)[0]  # Tomar el primer polígono si es multipolygon
    coords = list(polygon.exterior.coords)
    return [list(coord) for coord in coords]


def download_alerts(api_key: str, start_date: str, end_date: str, polygon: List[List[float]]) -> bytes:
    """
    Descarga datos de alertas GFW (alertas integradas) en formato CSV.

    Parámetros:
    - api_key (str): API key obtenida por `get_api_key()`.
    - start_date (str): Fecha de inicio en formato 'YYYY-MM-DD'.
    - end_date (str): Fecha de fin en formato 'YYYY-MM-DD'.
    - polygon (List[List[float]]): Coordenadas [[lon, lat], ...] de un polígono cerrado, extraídas desde archivo.

    Retorna:
    - bytes: Contenido del CSV (se puede guardar con `save_to_csv`).
    """
    url = "https://data-api.globalforestwatch.org/dataset/gfw_integrated_alerts/latest/download/csv"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [polygon]  # debe estar cerrado (primer punto igual al último)
        },
        "sql": (
            "SELECT longitude, latitude, gfw_integrated_alerts__date, "
            "gfw_integrated_alerts__confidence, umd_glad_landsat_alerts__confidence, "
            "umd_glad_sentinel2_alerts__confidence, wur_radd_alerts__confidence "
            f"FROM results WHERE gfw_integrated_alerts__date >= '{start_date}' "
            f"AND gfw_integrated_alerts__date <= '{end_date}'"
        )
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.content


def save_to_csv(data: bytes, filename: str):
    """
    Guarda un archivo CSV local a partir de contenido en bytes.

    Parámetros:
    - data (bytes): Contenido del archivo CSV (obtenido por `download_alerts`).
    - filename (str): Ruta y nombre del archivo de salida (ej. "alertas.csv").
    """
    with open(filename, 'wb') as f:
        f.write(data)

def csv_to_geodataframe(csv_path: str) -> gpd.GeoDataFrame:
    df = pd.read_csv(csv_path)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326"
    )
    return gdf

def summarize_alert_confidences(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    summary = {}
    for column in ALERT_COLUMNS:
        if column in df.columns:
            counts = df[column].value_counts().to_dict()
            column_summary = {str(level): count for level, count in counts.items()}
            column_summary["total"] = sum(counts.values())
            summary[column] = column_summary
    return summary


def save_geodataframe_to_geojson(gdf: gpd.GeoDataFrame, output_path: str):
    gdf.to_file(output_path, driver='GeoJSON')
    
def save_bbox_to_geojson(shapefile_path: str, output_path: str):
    area_gdf = gpd.read_file(shapefile_path)
    bbox = area_gdf.total_bounds  # xmin, ymin, xmax, ymax
    bbox_geom = box(bbox[0], bbox[1], bbox[2], bbox[3])
    bbox_poly = gpd.GeoDataFrame(geometry=[bbox_geom], crs="EPSG:4326")
    bbox_poly.to_file(output_path, driver='GeoJSON')



def plot_alerts_with_boundaries(alerts_gdf: gpd.GeoDataFrame, shapefile_path: str, output_path: str, start_date: str, end_date: str, bbox_color="black"):
    # Proyección a Web Mercator
    area_gdf = gpd.read_file(shapefile_path).to_crs(epsg=3857)
    alerts_gdf = alerts_gdf.to_crs(epsg=3857)

    bbox = area_gdf.total_bounds
    bbox_geom = box(bbox[0], bbox[1], bbox[2], bbox[3])
    bbox_poly = gpd.GeoDataFrame(geometry=[bbox_geom], crs="EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10))
    area_gdf.boundary.plot(ax=ax, edgecolor="blue", linewidth=1, label="Área")
    bbox_poly.boundary.plot(ax=ax, edgecolor=bbox_color, linestyle="--", linewidth=1, label="Bounding Box")
    alerts_gdf.plot(ax=ax, color="red", markersize=5, alpha=0.6, label="Alertas")

    try:
        ctx.add_basemap(ax, crs=alerts_gdf.crs, source=ctx.providers.OpenStreetMap.Mapnik)
    except Exception as e:
        print(f"⚠️ No se pudo cargar el basemap: {e}")

    ax.set_axis_off()
    ax.set_title(f"Alertas integradas de deforestación entre {start_date} y {end_date}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
