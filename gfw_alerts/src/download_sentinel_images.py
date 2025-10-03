import ee
import geemap
import os

from shapely.geometry import Polygon
from datetime import datetime, timedelta

def authenticate_gee(project='bosques-bogota-416214'):
    try:
        ee.Initialize(project=project)
    except Exception:
        print("🔐 Autenticando por primera vez...")
        ee.Authenticate()
        ee.Initialize(project=project)

def download_sentinel_rgb_for_region(region_geom, start_date, end_date, output_path):
    """
    Descarga imagen Sentinel-2 RGB para una región (Polygon) en fechas dadas.
    """
    if isinstance(region_geom, Polygon):
        region = ee.Geometry.Polygon(list(region_geom.exterior.coords))
    else:
        raise ValueError("La geometría debe ser Polygon.")

    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(region)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                  .select(['B4', 'B3', 'B2']))
    
    if collection.size().getInfo() == 0:
        # ⚠️ No encontró nada → ampliar 3 meses hacia atrás
        new_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
        print(f"⚠️ No se encontraron imágenes entre {start_date} y {end_date}. "
              f"Ampliando rango desde {new_start} a {end_date}.")

        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(region)
                      .filterDate(new_start, end_date)
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                      .select(['B4', 'B3', 'B2']))
        image = collection.median().clip(region)
        
        geemap.download_ee_image(
        image=image,
        filename=output_path,
        region=region,
        scale=10,
        crs="EPSG:4326")
        
        return f"Dado que no se encontraron imágenes vádilas en el trimestre seleccionado, se amplió el rango de búsqueda del {new_start} al {end_date}"


    image = collection.median().clip(region)

    geemap.download_ee_image(
        image=image,
        filename=output_path,
        region=region,
        scale=10,
        crs="EPSG:4326"
    )
    
    return None
    

def download_clusters(clusters_bboxes_gdf, start_date, end_date, output_dir):
    """
    Descarga 1 imagen Sentinel RGB por cluster_id, usando el bbox.
    """
    os.makedirs(output_dir, exist_ok=True)

    for _, row in clusters_bboxes_gdf.iterrows():
        region = row.geometry
        cluster_id = row["cluster_id"]

        output_path = os.path.join(output_dir, f"sentinel_cluster_{cluster_id}.tif")
        download_sentinel_rgb_for_region(region, start_date, end_date, output_path)
