import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import os
import rasterio
import folium
import ee
import json
from matplotlib_scalebar.scalebar import ScaleBar

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

def plot_sentinel_cluster_interactive(
    cluster_geom,
    cluster_id,
    start_date,
    end_date,
    output_path,
    alerts_gdf=None,
    cloudy=30,
    project=None
):
    """
    Genera un mapa interactivo con:
    - Imagen Sentinel-2 RGB (Earth Engine)
    - Basemap CartoDB Positron
    - Borde del cluster
    - Puntos de alertas (solo las de nivel 'highest')
    - Leyenda fija en pantalla
    """

    ee.Initialize(project=project)

    # === Convertir geometría del cluster a EE ===
    geom = ee.Geometry.Polygon(cluster_geom.exterior.coords[:])
    vis_params = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"], "gamma": 1.1}

    # === Crear colección Sentinel-2 filtrada ===
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloudy))
        .select(["B4", "B3", "B2"])
    )

    if col.size().getInfo() == 0:
        print(f"⚠️ Cluster {cluster_id}: sin imágenes disponibles")
        return None

    img = col.median().clip(geom)
    tile_url = img.getMapId(vis_params)["tile_fetcher"].url_format

    # === Crear mapa base ===
    centroid = cluster_geom.centroid
    m = folium.Map(
        location=[centroid.y, centroid.x],
        zoom_start=12,
        tiles="CartoDB positron",
        attr="CartoDB Positron"
    )

    # === Capa Sentinel-2 ===
    folium.TileLayer(
        tiles=tile_url,
        name=f"Sentinel-2 ({start_date} a {end_date})",
        attr="Sentinel-2 EE",
        overlay=True,
        show=True
    ).add_to(m)

    # === Borde del cluster ===
    gdf_cluster = gpd.GeoDataFrame(geometry=[cluster_geom], crs="EPSG:4326")
    folium.GeoJson(
        json.loads(gdf_cluster.to_json()),
        name=f"Cluster {cluster_id}",
        style_function=lambda x: {"color": "red", "weight": 2, "fillOpacity": 0},
        show=True
    ).add_to(m)

    # === Puntos de alertas (solo las de confianza highest) ===
    if alerts_gdf is not None:
        try:
            alerts_gdf = alerts_gdf.to_crs("EPSG:4326")
            alerts_in_cluster = alerts_gdf[
                (alerts_gdf.within(cluster_geom)) &
                (alerts_gdf["gfw_integrated_alerts__confidence"] == "highest")
            ]

            for _, row in alerts_in_cluster.iterrows():
                folium.CircleMarker(
                    location=[row.geometry.y, row.geometry.x],
                    radius=5,
                    color="#FF0000",
                    fill=True,
                    fill_color="#FF0000",
                    fill_opacity=0.85
                ).add_to(m)

            if not alerts_in_cluster.empty:
                m.fit_bounds(alerts_in_cluster.total_bounds.tolist())
            else:
                m.fit_bounds(gdf_cluster.total_bounds.tolist())
        except Exception as e:
            print(f"⚠️ No se pudieron agregar alertas al cluster {cluster_id}: {e}")

    # === Leyenda fija ===
    legend_html = """
    <div style="
        position: fixed;
        bottom: 20px;
        left: 20px;
        width: 170px;
        background-color: white;
        border: 1px solid grey;
        border-radius: 6px;
        z-index: 9999;
        font-size: 13px;
        padding: 10px;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
    ">
        <b>Leyenda</b><br>
        <i style="background:#FF0000; width:12px; height:12px;
                  float:left; margin-right:8px; opacity:0.85;
                  border-radius:50%;"></i>
        Alerta de deforestación<br>
        <i style="border:2px solid red; width:12px; height:12px;
                  float:left; margin-right:8px;"></i>
        Límite del cluster
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # === Control de capas ===
    folium.LayerControl(collapsed=False).add_to(m)

    # === Guardar mapa ===
    try:
        m.save(output_path)
        print(f"✅ Mapa interactivo del cluster {cluster_id} guardado en: {output_path}")
        return output_path
    except Exception as e:
        print(f"❌ Error generando mapa para cluster {cluster_id}: {e}")
        return None
