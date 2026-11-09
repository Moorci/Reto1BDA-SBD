
import csv
from pathlib import Path
from openpyxl import load_workbook

# ============================================================
# CONFIGURACION
# ============================================================

ARCHIVO_EXCEL = Path(
    "originales/fotocasa/MunicipiosCAE_2025_19_02.xlsx"
)

ARCHIVO_SALIDA = Path(
    "originales/fotocasa/catalogo_municipios_fotocasa.csv"
)

PROVINCIAS = {
    "01": "Álava",
    "48": "Bizkaia",
    "20": "Gipuzkoa"
}

# Municipios cuya página de Fotocasa ya hemos comprobado.
FOTOCASA_VALIDADO = {
    "48020": {
        "id": "48020",
        "slug": "bilbao",
        "nombre": "Bilbao",
        "alquiler": 82,
        "venta": 82
    },
    "01059": {
        "id": "1059",
        "slug": "vitoria-gasteiz",
        "nombre": "Vitoria - Gasteiz",
        "alquiler": 82,
        "venta": 82
    },
    "48013": {
        "id": "48013",
        "slug": "barakaldo",
        "nombre": "Barakaldo",
        "alquiler": 82,
        "venta": 82
    },
    "20069": {
        "id": "20069",
        "slug": "donostia-san-sebastian",
        "nombre": "Donostia - San Sebastián",
        "alquiler": 82,
        "venta": 82
    },
    "01002": {
        "id": "1002",
        "slug": "amurrio",
        "nombre": "Amurrio",
        "alquiler": 82,
        "venta": 82
    }
}


# ============================================================
# FUNCIONES
# ============================================================

def normalizar_codigo(valor, longitud):
    """Convierte un código Excel en una cadena con ceros."""

    if valor is None:
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    if not texto.isdigit():
        return ""

    return texto.zfill(longitud)


# ============================================================
# COMPROBACIONES INICIALES
# ============================================================

if not ARCHIVO_EXCEL.exists():
    raise FileNotFoundError(
        f"No se encuentra el Excel: {ARCHIVO_EXCEL}"
    )

libro = load_workbook(
    ARCHIVO_EXCEL,
    read_only=True,
    data_only=True
)

hoja = libro["EAE"]

municipios = []

# ============================================================
# EXTRACCION DE MUNICIPIOS
# ============================================================

for fila in hoja.iter_rows(min_row=10, values_only=True):

    codigo_provincia = normalizar_codigo(fila[0], 2)
    codigo_municipio = normalizar_codigo(fila[2], 3)

    nombre = fila[3]

    if not codigo_provincia or not codigo_municipio:
        continue

    if codigo_provincia not in PROVINCIAS:
        continue

    if nombre is None:
        continue

    nombre = str(nombre).strip()

    codigo_ine = codigo_provincia + codigo_municipio

    municipios.append({
        "municipio_codigo": codigo_ine,
        "municipio_oficial": nombre,
        "provincia": PROVINCIAS[codigo_provincia]
    })

libro.close()

# ============================================================
# VALIDACIONES
# ============================================================

codigos = [
    m["municipio_codigo"]
    for m in municipios
]

duplicados = sorted({
    codigo for codigo in codigos
    if codigos.count(codigo) > 1
})

if duplicados:
    raise ValueError(
        f"Hay códigos municipales duplicados: {duplicados}"
    )

if len(municipios) != 252:
    raise ValueError(
        f"Se esperaban 252 municipios y se han encontrado {len(municipios)}. Revisar el Excel."
    )

# Comprobar distribución provincial.
conteo_provincias = {}

for municipio in municipios:
    provincia = municipio["provincia"]
    conteo_provincias[provincia] = (
        conteo_provincias.get(provincia, 0) + 1
    )

# ============================================================
# CONSTRUCCION DEL CATALOGO FOTOCASA
# ============================================================

catalogo = []

for municipio in municipios:

    codigo = municipio["municipio_codigo"]

    datos_fc = FOTOCASA_VALIDADO.get(codigo)

    if datos_fc:

        fotocasa_id = datos_fc["id"]
        slug = datos_fc["slug"]
        nombre_fc = datos_fc["nombre"]

        url = (
            "https://www.fotocasa.es/es/indice-precio-vivienda/"
            f"alquiler/{slug}/todas-las-zonas"
        )

        estado = "validado"
        registros_alquiler = datos_fc["alquiler"]
        registros_venta = datos_fc["venta"]

    else:

        fotocasa_id = ""
        slug = ""
        nombre_fc = ""
        url = ""
        estado = "pendiente"
        registros_alquiler = ""
        registros_venta = ""

    catalogo.append({
        "municipio_codigo": codigo,
        "municipio_oficial": municipio["municipio_oficial"],
        "provincia": municipio["provincia"],
        "fotocasa_id": fotocasa_id,
        "fotocasa_slug": slug,
        "nombre_fotocasa": nombre_fc,
        "url": url,
        "estado": estado,
        "registros_alquiler": registros_alquiler,
        "registros_venta": registros_venta
    })

# ============================================================
# GUARDAR CSV
# ============================================================

ARCHIVO_SALIDA.parent.mkdir(
    parents=True,
    exist_ok=True
)

columnas = [
    "municipio_codigo",
    "municipio_oficial",
    "provincia",
    "fotocasa_id",
    "fotocasa_slug",
    "nombre_fotocasa",
    "url",
    "estado",
    "registros_alquiler",
    "registros_venta"
]

with open(
    ARCHIVO_SALIDA,
    "w",
    newline="",
    encoding="utf-8-sig"
) as archivo:

    escritor = csv.DictWriter(
        archivo,
        fieldnames=columnas,
        delimiter=";"
    )

    escritor.writeheader()
    escritor.writerows(catalogo)

# ============================================================
# INFORME
# ============================================================

validados = sum(
    1 for m in catalogo
    if m["estado"] == "validado"
)

pendientes = sum(
    1 for m in catalogo
    if m["estado"] == "pendiente"
)

print("=" * 65)
print("CATALOGO DE MUNICIPIOS DE EUSKADI")
print("=" * 65)

print(f"\nTotal de municipios: {len(catalogo)}")
print(f"Municipios validados en Fotocasa: {validados}")
print(f"Municipios pendientes: {pendientes}")

print("\nDISTRIBUCION POR PROVINCIA")

for provincia, cantidad in sorted(conteo_provincias.items()):
    print(f"{provincia}: {cantidad}")

print("\nCOMPROBACION DE CODIGOS")
print("Códigos duplicados:", len(duplicados))
print("Longitud correcta:",
      all(len(c) == 5 for c in codigos))

print("\nARCHIVO GENERADO:")
print(ARCHIVO_SALIDA)
