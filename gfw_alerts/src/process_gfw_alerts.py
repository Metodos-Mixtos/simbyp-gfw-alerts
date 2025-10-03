import geopandas as gpd
import pandas as pd
import warnings
import numpy as np
import matplotlib.pyplot as plt
import os
import rasterio
import json
import folium

from matplotlib_scalebar.scalebar import ScaleBar
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


def cluster_alerts_by_section(alerts_gdf: gpd.GeoDataFrame, buffer_m=250) -> gpd.GeoDataFrame:
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


def get_cluster_bboxes(alerts_clusters_gdf, buffer_m=900):
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

def create_cluster_maps(clusters_gdf, alerts_gdf, sentinel_images_dir, output_dir):
    """
    Crea mapas enriquecidos para TODOS los clusters.
    - Imagen Sentinel (GeoTIFF) como fondo usando rasterio
    - Puntos de alertas en rojo
    - Leyenda, flecha de norte y barra de escala
    """
    cluster_maps = []

    for cid, cluster in clusters_gdf.iterrows():
        sentinel_img = os.path.join(
            sentinel_images_dir,
            f"sentinel_cluster_{cluster['cluster_id']}.tif"
        )

        # Leer raster
        with rasterio.open(sentinel_img) as src:
            img = src.read([1, 2, 3])
            bounds = src.bounds
            transform = src.transform
            res = transform.a

        # Normalización simple para mejorar visualización
        img = img.astype(float)
        img = np.clip(img / np.percentile(img, 98), 0, 1)

        # Crear figura
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.imshow(
            img.transpose((1, 2, 0)),
            extent=[bounds.left, bounds.right, bounds.bottom, bounds.top]
        )

        # === Puntos de alerta en este cluster ===
        cluster_points = alerts_gdf[alerts_gdf["cluster_id"] == cluster["cluster_id"]]
        cluster_points.plot(ax=ax, color="red", markersize=30, label="Alerta")
        
        # Barra de escala
        scalebar = ScaleBar(dx=res, units="m", dimension="si-length", location="lower left", scale_loc="bottom", length_fraction=0.25) 
        ax.add_artist(scalebar)

        # Leyenda y flecha norte
        ax.legend(loc="lower right")
        ax.annotate(
            "N", xy=(0.95, 0.3), xytext=(0.95, 0.15),
            arrowprops=dict(facecolor='black', width=5, headwidth=15),
            ha='center', va='center', xycoords=ax.transAxes
        )

        ax.set_axis_off()

        # Guardar mapa enriquecido
        out_path = os.path.join(output_dir, f"cluster_{cluster['cluster_id']}_map.png")
        plt.savefig(out_path, dpi=150, bbox_inches="tight", transparent=True)
        plt.close()

        # Agregar entrada al listado de mapas
        cluster_maps.append({
            "cluster_id": cluster["cluster_id"],
            "map_path": out_path
        })

    return cluster_maps

def plot_alerts_interactive(alerts_gdf: gpd.GeoDataFrame, shapefile_path: str, output_path: str):
    """
    Crea un mapa interactivo con Folium:
    - Área de estudio con borde azul delgado
    - Alertas coloreadas (rojo = Muy alto, naranja = otras)
    - Popups en español
    - Leyenda fija en la esquina inferior izquierda
    """
    # Diccionario para traducir niveles de confianza
    translate_conf = {
        "highest": "Muy alto",
        "high": "Alto",
        "nominal": "Nominal",
        "not_detected": "No detectado"
    }

    # Convertir a lat/lon
    alerts_gdf = alerts_gdf.to_crs(epsg=4326)
    area_gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

    # Crear mapa centrado en el área de alertas
    center = [alerts_gdf.geometry.y.mean(), alerts_gdf.geometry.x.mean()]
    m = folium.Map(location=center, zoom_start=10, tiles="OpenStreetMap")

    # Añadir límites del polígono con borde azul delgado y fondo azul clarito
    folium.GeoJson(
        area_gdf.geometry,
        name="Área de estudio",
        style_function=lambda x: {
            "color": "blue",
            "weight": 1,
            "fillColor": "lightblue",
            "fillOpacity": 0.2
        }
    ).add_to(m)

    # Crear puntos de alertas con popups descriptivos
    for _, row in alerts_gdf.iterrows():
        conf = translate_conf.get(row.get("gfw_integrated_alerts__confidence"), "N/A")
        glad_landsat = translate_conf.get(row.get("umd_glad_landsat_alerts__confidence"), "N/A")
        glad_s2 = translate_conf.get(row.get("umd_glad_sentinel2_alerts__confidence"), "N/A")
        radd = translate_conf.get(row.get("wur_radd_alerts__confidence"), "N/A")

        color = "red" if conf == "Muy alto" else "orange"

        popup_html = f"""
        <b>Alerta</b><br>
        📍 Lat: {row.geometry.y:.5f}, Lon: {row.geometry.x:.5f}<br>
        GFW (Integrada): {conf}<br>
        GLAD Landsat: {glad_landsat}<br>
        GLAD Sentinel-2: {glad_s2}<br>
        RADD: {radd}
        """

        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=popup_html
        ).add_to(m)

    # Leyenda HTML fija, pegada a la esquina
    legend_html = """
    <div style="
        position: fixed;
        bottom: 20px; left: 20px; width: 160px; height: 80px;
        background-color: white;
        border:1px solid grey;
        z-index:9999;
        font-size:13px;
        padding: 8px;
    ">
    <b>Leyenda</b><br>
    <i style="background:red; width:12px; height:12px; float:left; margin-right:8px; opacity:0.7"></i> Muy alto<br>
    <i style="background:orange; width:12px; height:12px; float:left; margin-right:8px; opacity:0.7"></i> Otros
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Guardar el mapa
    m.save(output_path)