import geopandas as gpd
import pandas as pd
import warnings
import numpy as np
from sklearn.neighbors import BallTree


def process_alerts(alerts_path: str, veredas_path: str, secciones_path: str) -> gpd.GeoDataFrame:
    """
    Procesa las alertas de deforestación:
      - Filtra solo 'highest'
      - Cruza con veredas y secciones rurales
    """
    gfw_alerts = gpd.read_file(alerts_path)
    veredas = gpd.read_file(veredas_path)
    secciones = gpd.read_file(secciones_path, converters={'MPIO_CDPMP': 'str'})

    cols_to_filter = [
        'MPIO_CDPMP', 'SECR_CCNCT', 'STVIVIENDA', 'STP19_EC_1', 'STP19_ES_2',
        'STP19_ACU1', 'STP19_ACU2', 'STP19_ALC1', 'STP19_ALC2', 'STP19_GAS1',
        'STP19_GAS2', 'STP19_REC1', 'STP19_REC2', 'STP19_INT1', 'STP19_INT2',
        'STP27_PERS', 'pobdens20', 'gdp_20_m2p', 'acss_mrkt',
        'elevation', 'dprivt', 'treecv_24', 'geometry'
    ]
    secciones = secciones[cols_to_filter].copy()

    secciones['STVIVIENDA'] = pd.to_numeric(secciones['STVIVIENDA'], errors="coerce")
    base = secciones['STVIVIENDA'].mask(secciones['STVIVIENDA'] == 0)
    
    secciones['ENRG_PERC']  = secciones['STP19_EC_1'] / base * 100
    secciones['ACUED_PERC'] = secciones['STP19_ACU1'] / base * 100
    secciones['ALCLT_PERC'] = secciones['STP19_ALC1'] / base * 100
    secciones['GAS_PERC']   = secciones['STP19_GAS1'] / base * 100
    secciones['BASUR_PERC'] = secciones['STP19_REC1'] / base * 100
    secciones['INTER_PERC'] = secciones['STP19_INT1'] / base * 100

    gfw_alerts = gfw_alerts[gfw_alerts["gfw_integrated_alerts__confidence"] == "highest"]

    if gfw_alerts.empty:
        warnings.warn("⚠️ No se encontraron alertas con confianza 'highest'.", UserWarning)

    df = gpd.sjoin(gfw_alerts, veredas[['CODIGO_VER', 'NOMB_MPIO', 'NOMBRE_VER', 'geometry']], how='left')
    df = df.drop(columns='index_right', errors='ignore')
    df = gpd.sjoin(df, secciones, how='left')

    return df

def cluster_alerts_by_section(alerts_gdf: gpd.GeoDataFrame, buffer_m=1000) -> gpd.GeoDataFrame:
    """
    Agrupa alertas en clusters si sus buffers de 250m se intersectan
    y pertenecen a la misma sección rural (SECR_CCNCT).
    Devuelve los puntos originales con un cluster_id asignado.
    """
    utm_crs = alerts_gdf.estimate_utm_crs()
    alerts_proj = alerts_gdf.to_crs(utm_crs).copy()

    clusters = []
    cluster_id = 0

    for secr, group in alerts_proj.groupby("SECR_CCNCT"):
        coords = np.array([(geom.x, geom.y) for geom in group.geometry])
        tree = BallTree(coords, metric="euclidean")
        labels = -np.ones(len(group), dtype=int)

        for i in range(len(coords)):
            if labels[i] == -1:
                cluster_id += 1
                neighbors = tree.query_radius([coords[i]], r=2*buffer_m)[0]
                labels[neighbors] = cluster_id

        group["cluster_id"] = labels
        clusters.append(group)

    result = gpd.GeoDataFrame(pd.concat(clusters), crs=utm_crs)
    return result.to_crs(epsg=4326)


def get_cluster_bboxes(alerts_clusters_gdf, buffer_m=2000):
    """
    Genera un GeoDataFrame con un bbox (cuadrado) por cluster_id.
    """
    utm_crs = alerts_clusters_gdf.estimate_utm_crs()
    alerts_proj = alerts_clusters_gdf.to_crs(utm_crs)

    bboxes = []
    for cid, group in alerts_proj.groupby("cluster_id"):
        cluster_geom = group.geometry.buffer(buffer_m).unary_union.envelope
        bboxes.append({"cluster_id": cid, "geometry": cluster_geom})

    bboxes_gdf = gpd.GeoDataFrame(bboxes, crs=utm_crs)
    return bboxes_gdf.to_crs(epsg=4326)