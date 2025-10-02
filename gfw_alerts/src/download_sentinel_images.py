import ee
import geemap
import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from shapely.geometry import Polygon
from matplotlib_scalebar.scalebar import ScaleBar

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

    image = collection.median().clip(region)

    geemap.download_ee_image(
        image=image,
        filename=output_path,
        region=region,
        scale=10,
        crs="EPSG:4326"
    )

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
