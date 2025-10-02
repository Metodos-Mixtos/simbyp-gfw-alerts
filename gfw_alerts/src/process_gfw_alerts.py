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
        'STP27_PERS', 'popcount20', 'gdp_20_m2_', 'acss_mrkt',
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
        cluster_points.plot(ax=ax, color="red", markersize=20, label="Alerta")
        
        # Barra de escala
        scalebar = ScaleBar(10, units="m", location="lower left")  # Sentinel resolución = 10m
        ax.add_artist(scalebar)

        # Leyenda y flecha norte
        ax.legend(loc="lower right")
        ax.annotate(
            "N", xy=(0.95, 0.15), xytext=(0.95, 0.3),
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

def build_report_json(summary, alerts_with_clusters, cluster_maps, trimestre, anio, ruta_logo, ruta_mapa_alertas, output_path):
    """
    Construye un JSON consolidado con alertas, clusters y mapas enriquecidos.
    """
    # Base inicial
    report_data = {
        "TRIMESTRE": trimestre,
        "ANIO": anio,
        "LOGO": ruta_logo,
        "MAPA_ALERTAS": ruta_mapa_alertas,
        # GFW
        "GFW_NOMINAL": summary["gfw_integrated_alerts__confidence"].get("nominal", 0),
        "GFW_ALTO": summary["gfw_integrated_alerts__confidence"].get("high", 0),
        "GFW_MUY_ALTO": summary["gfw_integrated_alerts__confidence"].get("highest", 0),
        "GFW_TOTAL": summary["gfw_integrated_alerts__confidence"].get("total", 0),
        
        # GLAD Landsat
        "GLADL_NOMINAL": summary["umd_glad_landsat_alerts__confidence"].get("nominal", 0),
        "GLADL_ALTO": summary["umd_glad_landsat_alerts__confidence"].get("high", 0),
        "GLADL_NO_DET": summary["umd_glad_landsat_alerts__confidence"].get("not_detected", 0),
        "GLADL_TOTAL": summary["umd_glad_landsat_alerts__confidence"].get("total", 0),

        # GLAD Sentinel-2
        "GLADS_NOMINAL": summary["umd_glad_sentinel2_alerts__confidence"].get("nominal", 0),
        "GLADS_ALTO": summary["umd_glad_sentinel2_alerts__confidence"].get("high", 0),
        "GLADS_NO_DET": summary["umd_glad_sentinel2_alerts__confidence"].get("not_detected", 0),
        "GLADS_TOTAL": summary["umd_glad_sentinel2_alerts__confidence"].get("total", 0),

        # WUR RADD
        "RADD_NOMINAL": summary["wur_radd_alerts__confidence"].get("nominal", 0),
        "RADD_ALTO": summary["wur_radd_alerts__confidence"].get("high", 0),
        "RADD_NO_DET": summary["wur_radd_alerts__confidence"].get("not_detected", 0),
        "RADD_TOTAL": summary["wur_radd_alerts__confidence"].get("total", 0),
        "SECCIONES_MUY_ALTO": []
    }

    # Loop de clusters
    for _, row in alerts_with_clusters.drop_duplicates("cluster_id").iterrows():
        cid = row["cluster_id"]

        # Buscar el mapa asociado
        map_path = next((m["map_path"] for m in cluster_maps if m["cluster_id"] == cid), None)

        cluster_info = {
            "cluster_id": int(cid),
            "municipio": row.get("NOMB_MPIO", ""),
            "vereda": row.get("NOMBRE_VER", ""),
            "densidad_poblacional": row.get("popcount20", None),
            "pib_m2": row.get("gdp_20_m2_", None),
            "mercado_acceso": row.get("acss_mrkt", None),
            "elevacion": row.get("elevation", None),
            "ind_priv": row.get("dprivt", None),
            "cobertura_arboles": row.get("treecv_24", None),
            "energia_pct": row.get("ENRG_PERC", None),
            "acueducto_pct": row.get("ACUED_PERC", None),
            "alcantarillado_pct": row.get("ALCLT_PERC", None),
            "gas_pct": row.get("GAS_PERC", None),
            "basura_pct": row.get("BASUR_PERC", None),
            "internet_pct": row.get("INTER_PERC", None),
            "mapa_cluster": map_path
        }

        report_data["SECCIONES_MUY_ALTO"].append(cluster_info)

    # Guardar JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"✅ JSON final guardado en: {output_path}")
    return report_data

def plot_alerts_with_boundaries(alerts_gdf: gpd.GeoDataFrame, shapefile_path: str, output_path: str, start_date: str, end_date: str, bbox_color="black"):
    # Proyección a Web Mercator
    area_gdf = gpd.read_file(shapefile_path).to_crs(epsg=3857)
    alerts_gdf = alerts_gdf.to_crs(epsg=3857)

    bbox = area_gdf.total_bounds
    bbox_geom = box(bbox[0], bbox[1], bbox[2], bbox[3])
    bbox_poly = gpd.GeoDataFrame(geometry=[bbox_geom], crs="EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10), facecolor='none')
    area_gdf.boundary.plot(ax=ax, edgecolor="blue", linewidth=1, label="Área de estudio")
    #bbox_poly.boundary.plot(ax=ax, edgecolor=bbox_color, linestyle="--", linewidth=1, label="Bounding Box")
    alerts_gdf.plot(ax=ax, color="red", markersize=5, alpha=0.6, label="Alertas integradas")

    try:
        ctx.add_basemap(ax, crs=alerts_gdf.crs, source=ctx.providers.OpenStreetMap.Mapnik)
    except Exception as e:
        print(f"⚠️ No se pudo cargar el basemap: {e}")

    ax.set_axis_off()
    #ax.set_title(f"Alertas integradas de deforestación entre {start_date} y {end_date}")
    plt.legend(loc='upper left')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close()


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


    