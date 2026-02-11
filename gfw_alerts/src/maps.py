import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import os
import rasterio
import folium
from folium import plugins
import ee
import json
import requests
import base64
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
    # Primero dibujamos las alertas de menor prioridad, luego las "highest" para que queden encima
    for priority in ["nominal", "high", "highest"]:
        for _, row in alerts_gdf.iterrows():
            conf_raw = row.get("gfw_integrated_alerts__confidence")
            if conf_raw != priority:
                continue
                
            conf = translate_conf.get(conf_raw, "N/A")
            glad_landsat = translate_conf.get(row.get("umd_glad_landsat_alerts__confidence"), "N/A")
            glad_s2 = translate_conf.get(row.get("umd_glad_sentinel2_alerts__confidence"), "N/A")
            radd = translate_conf.get(row.get("wur_radd_alerts__confidence"), "N/A")

            # Alertas "highest" más grandes y visibles
            if conf == "Muy alto":
                color = "red"
                radius = 4
                weight = 3
                fill_opacity = 0.9
                z_index = 1000  # Encima de todo
            else:
                color = "orange"
                radius = 4
                weight = 3
                fill_opacity = 0.9
                z_index = 1

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
                radius=radius,
                color=color,
                weight=weight,
                fill=True,
                fill_opacity=fill_opacity,
                popup=popup_html,
                z_index_offset=z_index
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
    
    # Añadir minimapa en esquina superior derecha
    plugins.MiniMap(
        toggle_display=True,
        position='topright',
        width=150,
        height=150
    ).add_to(m)

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
    - Imagen Sentinel-2 RGB (Earth Engine) guardada como archivo PNG
    - Basemap CartoDB Positron (siempre visible)
    - Borde del cluster
    - Puntos de alertas (solo las de nivel 'highest')
    - Leyenda fija en pantalla
    - Advertencia si no hay imágenes con calidad óptima
    
    La imagen Sentinel se guarda como archivo PNG en el mismo directorio que el HTML.
    Si no hay imágenes disponibles, solo muestra basemap con advertencia.
    """

    ee.Initialize(project=project)
    
    import os
    import re
    from google.cloud import storage
    import requests
    from PIL import Image
    from io import BytesIO

    # Inicializar variables
    actual_resolution = None
    permanent_image_url = None
    cloud_warning = None
    actual_cloud_percent = None

    # === Convertir geometría del cluster a EE ===
    geom = ee.Geometry.Polygon(cluster_geom.exterior.coords[:])
    vis_params = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"], "gamma": 1.1}

    # === Crear colección Sentinel-2 filtrada (solo con calidad óptima) ===
    print(f"   🔍 Buscando imágenes Sentinel-2 para cluster {cluster_id}...")
    print(f"   📅 Rango: {start_date} a {end_date}")
    print(f"   ☁️  Filtro: <{cloudy}% cobertura de nubes")
    
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloudy))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
        .select(["B4", "B3", "B2"])
    )
    
    count_initial = col.size().getInfo()
    print(f"   📊 Imágenes encontradas con <{cloudy}% nubes: {count_initial}")
    
    cloud_warning = None
    has_images = False
    
    if count_initial == 0:
        print(f"   ⚠️  No se encontraron imágenes con <{cloudy}% de nubes")
        print(f"   ℹ️  Buscando imagen con menor cobertura de nubes disponible...")
        
        # Buscar TODAS las imágenes y ordenar por menor cobertura de nubes
        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(start_date, end_date)
            .sort("CLOUDY_PIXEL_PERCENTAGE")
            .select(["B4", "B3", "B2"])
        )
        count_all = col.size().getInfo()
        print(f"   📊 Total de imágenes disponibles: {count_all}")
        
        if count_all == 0:
            print(f"   ⚠️  No se encontraron imágenes Sentinel-2 en el período")
            permanent_image_url = None
            actual_resolution = None
            cloud_warning = f"No hay imágenes Sentinel-2 disponibles en este período"
            actual_cloud_percent = None
            has_images = False
        else:
            # Obtener la imagen menos nubosa
            first_img = ee.Image(col.first())
            actual_cloud_percent = first_img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
            
            # Usar la imagen individual (no median) cuando hay muchas nubes
            img = first_img.clip(geom)
            cloud_warning = f"Imagen con {actual_cloud_percent:.1f}% cobertura de nubes"
            print(f"   ℹ️  Usando imagen menos nubosa disponible: {actual_cloud_percent:.1f}%")
            has_images = True
    else:
        # Obtener la imagen menos nubosa
        first_img = ee.Image(col.first())
        actual_cloud_percent = first_img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
        
        # Con buena calidad, usar median para mejor resultado
        if count_initial >= 3:
            img = col.median().clip(geom)
            print(f"   ✅ Usando median de {count_initial} imágenes con {actual_cloud_percent:.1f}% nubes (mínimo)")
        else:
            img = first_img.clip(geom)
            print(f"   ✅ Usando imagen individual con {actual_cloud_percent:.1f}% de nubes")
        cloud_warning = None  # Imagen con buena calidad
        has_images = True
    
    # === Generar imagen solo si hay colección disponible ===
    if has_images:
        try:
            print(f"   ✅ Colección disponible, iniciando generación de imagen...")
            # === Calcular dimensiones para VERDADERA resolución de 10m ===
            bounds = cluster_geom.bounds  # (minx, miny, maxx, maxy)
            
            # Calcular dimensiones en metros (aproximado a latitud ~4.6°)
            import math
            lat_center = (bounds[1] + bounds[3]) / 2
            
            # 1 grado longitud ≈ 111km * cos(lat), 1 grado latitud ≈ 111km
            width_degrees = bounds[2] - bounds[0]
            height_degrees = bounds[3] - bounds[1]
            
            width_meters = width_degrees * 111000 * math.cos(math.radians(lat_center))
            height_meters = height_degrees * 111000
            
            # Píxeles necesarios para resolución de 10m
            width_pixels = int(width_meters / 10)
            height_pixels = int(height_meters / 10)
            
            # Limitar a máximo 8192x8192 (límite de Earth Engine)
            max_pixels = 8192
            if width_pixels > max_pixels or height_pixels > max_pixels:
                scale_factor = max(width_pixels / max_pixels, height_pixels / max_pixels)
                width_pixels = int(width_pixels / scale_factor)
                height_pixels = int(height_pixels / scale_factor)
                actual_resolution = 10 * scale_factor
            else:
                actual_resolution = 10
            
            dimensions = f'{width_pixels}x{height_pixels}'
            
            print(f"   📐 Área: {width_meters:.0f}m x {height_meters:.0f}m")
            print(f"   🖼️  Imagen: {width_pixels}x{height_pixels} píxeles")
            print(f"   📏 Resolución efectiva: ~{actual_resolution:.1f}m/píxel")
        
            thumb_url = img.getThumbURL({
                'dimensions': dimensions,
                'region': geom,
                'format': 'png',
                **vis_params
            })
            
            print(f"   📥 Descargando imagen Sentinel-2 para cluster {cluster_id}...")
            
            # Descargar imagen
            response = requests.get(thumb_url)
            print(f"   📡 Respuesta del servidor: status {response.status_code}")
            if response.status_code != 200:
                print(f"   ❌ Error descargando imagen: {response.status_code}")
                permanent_image_url = None
                image_base64 = None
                actual_resolution = None  # No se pudo descargar
                cloud_warning = "Error al descargar la imagen satelital"
            else:
                print(f"   📊 Tamaño de imagen descargada: {len(response.content)} bytes")
                
                # Validar que la imagen no esté vacía o corrupta (mínimo 50KB)
                if len(response.content) < 50000:
                    print(f"   ⚠️  Imagen demasiado pequeña ({len(response.content)} bytes), probablemente vacía")
                    permanent_image_url = None
                    actual_resolution = None
                    cloud_warning = f"Sin imagen Sentinel-2 útil ({actual_cloud_percent:.1f}% nubes)"
                else:
                    # Guardar imagen como archivo PNG
                    png_filename = f"sentinel_cluster_{cluster_id}.png"
                    png_path = os.path.join(os.path.dirname(output_path), png_filename)
                    
                    with open(png_path, 'wb') as f:
                        f.write(response.content)
                    
                    # Usar ruta absoluta para Folium (la convertirá a base64 automáticamente)
                    permanent_image_url = png_path
                    print(f"   ✅ Imagen guardada como PNG: {png_path}")
                    print(f"   📄 Folium convertirá a base64 automáticamente")
        except Exception as e:
            print(f"   ❌ Error generando imagen: {str(e)}")
            import traceback
            traceback.print_exc()
            permanent_image_url = None
            actual_resolution = None
            cloud_warning = f"Error generando imagen: {str(e)}"
    else:
        print(f"   ⚠️  No hay imágenes disponibles, saltando generación")

    # === Crear mapa base ===
    centroid = cluster_geom.centroid
    m = folium.Map(
        location=[centroid.y, centroid.x],
        zoom_start=14,
        tiles="CartoDB positron",
        attr="CartoDB Positron"
    )
    
    # Añadir minimapa en esquina superior derecha
    plugins.MiniMap(
        toggle_display=True,
        position='topright',
        width=150,
        height=150
    ).add_to(m)

    # === Capa Sentinel-2 como ImageOverlay permanente (si existe) ===
    if permanent_image_url:
        bounds = cluster_geom.bounds  # (minx, miny, maxx, maxy)
        folium.raster_layers.ImageOverlay(
            image=permanent_image_url,
            bounds=[[bounds[1], bounds[0]], [bounds[3], bounds[2]]],  # [[south, west], [north, east]]
            name=f"Sentinel-2 ({start_date} a {end_date})",
            overlay=True,
            opacity=0.8,
            interactive=True,
            cross_origin=False,
            zindex=1
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
        
        # Si hay PNG guardado, modificar el HTML para usar ruta relativa en lugar de base64
        if permanent_image_url and os.path.exists(permanent_image_url):
            png_filename = os.path.basename(permanent_image_url)
            
            # Leer el HTML generado
            with open(output_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Buscar y reemplazar data URL por ruta relativa
            # Folium convierte la imagen a base64, necesitamos revertir eso
            # Buscar el patrón de ImageOverlay con data:image/png;base64
            pattern = r'(var img_\w+ = L\.imageOverlay\(\s*)"data:image/png;base64,[^"]*"'
            replacement = rf'\1"{png_filename}"'
            html_content_modified = re.sub(pattern, replacement, html_content)
            
            # Guardar HTML modificado
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content_modified)
            
            print(f"   ✅ HTML modificado para usar PNG externo: {png_filename}")
        
        return output_path
    except Exception as e:
        print(f"❌ Error generando mapa para cluster {cluster_id}: {e}")
        return None
