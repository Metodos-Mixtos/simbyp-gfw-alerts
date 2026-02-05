# Sistema Monitoreo de Bosques y Páramos de Bogotá (SIMBYP) - Alertas GFW

Este repositorio contiene herramientas para el análisis y monitoreo de alertas de deforestación en Bogotá, integrando la API de Global Forest Watch (GFW) para descargar y procesar alertas integradas de deforestación.

## Estructura del Repositorio
- `main.py`: Script principal para ejecutar el pipeline completo de alertas GFW.
  - Modo semanal: sin argumentos, genera reporte de la semana anterior
  - Modo trimestral: con `--trimestre` y `--anio`, genera reporte trimestral
- `src/`: Módulos del pipeline.
  - `download_gfw_data.py`: Descarga de datos desde GFW API.
  - `process_gfw_alerts.py`: Procesamiento y enriquecimiento de alertas.
  - `create_final_json.py`: Construcción del JSON consolidado para reportes.
  - `maps.py`: Generación de mapas interactivos.
- `reporte/`: Renderizado de reportes HTML.
  - `render_report.py`: Lógica de renderizado.
  - `report_template.html`: Plantilla HTML para reportes.
- `requirements.txt`: Dependencias Python.
- `.gitignore`: Archivos ignorados por Git.

Frecuencia recomendada: Semanal (automática) o Trimestral (manual).

## Dependencies

Instala las dependencias con `pip install -r requirements.txt`:

- python-dotenv
- requests
- geopandas
- pandas
- shapely
- matplotlib
- contextily
- ee
- geemap
- matplotlib-scalebar
- gcsfs
- google-cloud-storage
- scikit-learn
- tenacity

## Configuration

Crea un archivo `.env` en la raíz con variables de entorno requeridas (credenciales GFW, rutas GCS, etc.). Consulta 'MMC - General - SDP - Monitoreo de Bosques/monitoreo_bosques/dot_env_content.txt' para detalles.

## Usage

El script principal puede ejecutarse en dos modos:

### 1. Reporte Semanal (sin parámetros)

Para generar un reporte de las alertas de deforestación de la semana anterior:

```bash
python main.py
```

Este comando generará automáticamente un reporte con las alertas desde el lunes hasta el domingo de la semana anterior a la fecha actual.

### 2. Reporte Trimestral (con parámetros)

Ejecuta el script con trimestre (I, II, III, IV) y año (YYYY):

```bash
python main.py --trimestre I --anio 2024
```

**Ejemplos:**
```bash
# Reporte del primer trimestre de 2024
python main.py --trimestre I --anio 2024

# Reporte del cuarto trimestre de 2023
python main.py --trimestre IV --anio 2023

# Reporte semanal automático
python main.py
```

Ambos modos descargan alertas GFW, las procesan, generan mapas y reportes, y suben los resultados a Google Cloud Storage.

## Colaboradores

Mantenido por el equipo de Métodos Mixtos (Daniel Wiesner, Javier Guerra, Samuel Blanco, Laura Tamayo). Para sugerencias, crea un Issue o Pull Request.

## Set-up

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install --upgrade pip setuptools wheel`
- `pip install -r requirements.txt`
- Crea el archivo `.env` con las variables requeridas.

## Licencia

Licencia pública. Código propiedad de la Secretaría Distrital de Planeación de Bogotá.
