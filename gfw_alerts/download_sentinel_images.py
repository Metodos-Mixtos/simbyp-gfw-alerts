# gee_image_download.py

import ee
import geemap
from shapely.geometry import Polygon, MultiPolygon
import geopandas as gpd
import os

def authenticate_gee(project='bosques-bogota-416214'):
    try:
        ee.Initialize(project=project)
    except Exception:
        print("🔐 Autenticando por primera vez...")
        ee.Authenticate()
        ee.Initialize(project=project)

def load_geometry(path):
    gdf = gpd.read_file(path)
    geom = gdf.geometry.iloc[0]

    if isinstance(geom, Polygon):
        return ee.Geometry.Polygon(list(geom.exterior.coords))
    elif isinstance(geom, MultiPolygon):
        poly = list(geom.geoms)[0]
        return ee.Geometry.Polygon(list(poly.exterior.coords))
    else:
        raise ValueError("La geometría no es Polygon ni MultiPolygon")

def download_sentinel_rgb_around_point(point_geom, start_date, end_date, output_path, buffer_m=50):
    lon, lat = point_geom.x, point_geom.y
    center = ee.Geometry.Point([lon, lat])
    region = center.buffer(buffer_m).bounds()

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
