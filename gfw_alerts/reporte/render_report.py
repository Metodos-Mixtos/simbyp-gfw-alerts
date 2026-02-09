#!/usr/bin/env python3
import json, re, base64
from pathlib import Path
from google.cloud import storage

SECTION_PAT = re.compile(r"{{#(\w+)}}(.*?){{/\1}}", re.DOTALL)
TOKEN_PAT   = re.compile(r"{{\s*([\w\.]+)\s*}}")

def gcs_image_to_base64(gcs_path):
    """
    Convierte una imagen en GCS a data URL base64 para incrustar en HTML.
    Si no es ruta GCS, devuelve la ruta original.
    """
    if not isinstance(gcs_path, str) or not gcs_path.startswith("gs://"):
        return gcs_path
    
    try:
        _, rest = gcs_path.split("gs://", 1)
        bucket_name, blob_path = rest.split("/", 1)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        # Descargar imagen
        image_bytes = blob.download_as_bytes()
        
        # Determinar MIME type por extensión
        ext = blob_path.lower().split('.')[-1]
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'svg': 'image/svg+xml'
        }
        mime_type = mime_types.get(ext, 'image/png')
        
        # Convertir a base64
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        return f"data:{mime_type};base64,{b64}"
    except Exception as e:
        print(f"⚠️ Error convirtiendo {gcs_path} a base64: {e}")
        return gcs_path  # Devolver ruta original en caso de error

def build_very_high_sections(sections):
    blocks = []
    for i, sec in enumerate(sections or [], start=1):
        bullets = "".join(f"<li>{b}</li>" for b in sec.get("bullets", []))
        block = f"""
        <div class="card">
          <h4 class="badge">Sección {i}</h4>
          <h3>{sec.get("title","Sección")}</h3>
          <ul>{bullets}</ul>
          <figure>
            <img src="{sec.get("image","#")}" alt="{sec.get("title","Sección")}" style="width:100%; border-radius:4px; border:1px solid #ccc;">
            <figcaption>Figura {i+1}. Imagen de Sentinel-2 para la sección {i}.</figcaption>
          </figure>
        </div>
        """
        blocks.append(block)
    return "\n".join(blocks)

def build_header(header_dict):
    if not isinstance(header_dict, dict):
        return ""
    logo = header_dict.get("LOGO", "#")
    alt = header_dict.get("ALT", "Header logo")
    height = header_dict.get("HEIGHT", "60px")
    return f"""
    <header>
      <img src="{logo}" alt="{alt}" style="height:{height};">
    </header>
    """

def _read_text(path):
    p = str(path)
    if p.startswith("gs://"):
        # parse gs://bucket/path/to/blob
        _, rest = p.split("gs://", 1)
        bucket_name, blob_path = rest.split("/", 1)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob.download_as_bytes().decode("utf-8")
    else:
        return Path(p).read_text(encoding="utf-8")

def _write_text(path, content):
    p = str(path)
    if p.startswith("gs://"):
        _, rest = p.split("gs://", 1)
        bucket_name, blob_path = rest.split("/", 1)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(content, content_type="text/html; charset=utf-8")
    else:
        Path(p).write_text(content, encoding="utf-8")

def render(template_path: Path, data_path: Path, out_path: Path):
    template = _read_text(template_path)
    data = json.loads(_read_text(data_path))

    # Convertir rutas GCS de imágenes a base64 para incrustar en HTML
    print("🖼️  Procesando imágenes...")
    if data.get("HEADER_IMG1"):
        data["HEADER_IMG1"] = gcs_image_to_base64(data["HEADER_IMG1"])
        print(f"   ✅ Header 1 procesado")
    if data.get("HEADER_IMG2"):
        data["HEADER_IMG2"] = gcs_image_to_base64(data["HEADER_IMG2"])
        print(f"   ✅ Header 2 procesado")
    if data.get("FOOTER_IMG"):
        data["FOOTER_IMG"] = gcs_image_to_base64(data["FOOTER_IMG"])
        print(f"   ✅ Footer procesado")

    # Convierte el dict HEADER a HTML antes de renderizar
    data["HEADER"] = build_header(data.get("HEADER"))

    # Renderiza tokens + secciones
    html = render_template(template, data)

    _write_text(out_path, html)
    return out_path

def render_template(tpl: str, root: dict) -> str:
    def _render_block(block: str, ctx: dict) -> str:
        def _section(m):
            key, inner = m.group(1), m.group(2)
            arr = ctx.get(key, [])
            if not isinstance(arr, list):
                return ""
            out = []
            for item in arr:
                local = {**ctx, **(item if isinstance(item, dict) else {".": item})}
                out.append(_render_block(inner, local))
            return "".join(out)

        out = SECTION_PAT.sub(_section, block)

        def _token(m):
            k = m.group(1)
            return str(ctx.get(k, root.get(k, "")))
        return TOKEN_PAT.sub(_token, out)

    return _render_block(tpl, root)
