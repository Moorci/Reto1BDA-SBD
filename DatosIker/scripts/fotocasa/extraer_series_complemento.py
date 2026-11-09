
import csv
import json
import re
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURACION
# ============================================================

ARCHIVO_CATALOGO = Path(
    "originales/fotocasa/catalogo_municipios_fotocasa.csv"
)

CARPETA_HTML = Path("originales/fotocasa")
CARPETA_SALIDA = Path("procesados/fotocasa")

ARCHIVO_CSV = CARPETA_SALIDA / "series_historicas_complemento.csv"
ARCHIVO_JSON = CARPETA_SALIDA / "series_historicas_complemento.json"

REGISTROS_ESPERADOS = 82

# Codigo INE y nombre del HTML original.
ARCHIVOS = {
    "01059": "vitoria-gasteiz_indice_alquiler.html",
    "48013": "barakaldo_indice_alquiler.html",
    "20069": "donostia-san-sebastian_indice_alquiler.html",
    "01002": "amurrio_indice_alquiler.html"
}


# ============================================================
# FUNCIONES
# ============================================================

def extraer_json(html):
    patron = (
        r"""<script\b(?=[^>]*\bid=["']__initial_props__["'])"""
        r"""[^>]*>(.*?)</script>"""
    )

    coincidencia = re.search(
        patron, html,
        flags=re.IGNORECASE | re.DOTALL
    )

    if not coincidencia:
        raise ValueError("No se encuentra __initial_props__")

    return json.loads(coincidencia.group(1))


def buscar_municipio(objeto):
    if isinstance(objeto, dict):

        if "priceEvolution" in objeto and "id" in objeto:
            return objeto

        for valor in objeto.values():
            resultado = buscar_municipio(valor)

            if resultado is not None:
                return resultado

    elif isinstance(objeto, list):

        for elemento in objeto:
            resultado = buscar_municipio(elemento)

            if resultado is not None:
                return resultado

    return None


def normalizar_fecha(valor):
    texto = str(valor).strip()

    if re.fullmatch(r"\d{8}", texto):
        return datetime.strptime(
            texto, "%Y%m%d"
        ).strftime("%Y-%m")

    raise ValueError(f"Fecha no reconocida: {valor}")


def convertir_precio(valor):
    if isinstance(valor, bool) or valor is None:
        raise ValueError(f"Precio no válido: {valor}")

    precio = float(valor)

    if precio <= 0:
        raise ValueError(f"Precio no positivo: {valor}")

    return precio


def extraer_serie(serie, municipio, tipo, id_fotocasa,
                  nombre_fotocasa):

    if not isinstance(serie, list):
        raise ValueError(
            f"Serie no válida: {municipio}, {tipo}"
        )

    if len(serie) != REGISTROS_ESPERADOS:
        raise ValueError(
            f"{municipio}, {tipo}: se esperaban "
            f"{REGISTROS_ESPERADOS} registros y hay {len(serie)}"
        )

    registros = []

    for elemento in serie:

        if not isinstance(elemento, dict):
            raise ValueError(f"Registro inesperado: {elemento}")

        if "period" not in elemento or "meanPriceSqm" not in elemento:
            raise ValueError(
                f"Campos inesperados: {list(elemento.keys())}"
            )

        fecha = normalizar_fecha(elemento["period"])
        precio = convertir_precio(elemento["meanPriceSqm"])

        registros.append({
            "municipio_codigo": municipio["municipio_codigo"],
            "municipio_oficial": municipio["municipio_oficial"],
            "fotocasa_id": id_fotocasa,
            "nombre_fotocasa": nombre_fotocasa,
            "tipo": tipo,
            "fecha": fecha,
            "precio_eur_m2": precio
        })

    registros.sort(key=lambda x: x["fecha"])

    fechas = [r["fecha"] for r in registros]

    if len(fechas) != len(set(fechas)):
        raise ValueError(
            f"Fechas duplicadas: {municipio['municipio_oficial']}, {tipo}"
        )

    return registros


# ============================================================
# LEER CATALOGO
# ============================================================

with open(
    ARCHIVO_CATALOGO,
    encoding="utf-8-sig",
    newline=""
) as archivo:

    catalogo = list(
        csv.DictReader(archivo, delimiter=";")
    )

catalogo_por_codigo = {
    fila["municipio_codigo"]: fila
    for fila in catalogo
}

municipios = []

for codigo, nombre_html in ARCHIVOS.items():

    if codigo not in catalogo_por_codigo:
        raise ValueError(
            f"No existe el municipio {codigo} en el catálogo"
        )

    municipios.append(catalogo_por_codigo[codigo])


# ============================================================
# EXTRAER SERIES
# ============================================================

CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

todos_los_registros = []
resumen = []

print("=" * 65)
print("EXTRACCION DE SERIES COMPLEMENTARIAS FOTOCASA")
print("=" * 65)

for municipio in municipios:

    codigo = municipio["municipio_codigo"]
    nombre = municipio["municipio_oficial"]
    nombre_archivo = ARCHIVOS[codigo]

    archivo_html = CARPETA_HTML / nombre_archivo

    print(f"\nMunicipio: {nombre}")
    print("Archivo:", archivo_html)

    if not archivo_html.exists():
        raise FileNotFoundError(archivo_html)

    html = archivo_html.read_text(encoding="utf-8")

    datos = extraer_json(html)
    objeto = buscar_municipio(datos)

    if objeto is None:
        raise ValueError(
            f"No se encuentra el municipio: {nombre}"
        )

    id_fotocasa = str(objeto.get("id", ""))

    if id_fotocasa != municipio["fotocasa_id"]:
        raise ValueError(
            f"ID diferente para {nombre}: "
            f"{id_fotocasa} != {municipio['fotocasa_id']}"
        )

    nombre_fotocasa = str(objeto.get("name", ""))

    evolucion = objeto.get("priceEvolution", {})

    for tipo, clave in [
        ("alquiler", "rent"),
        ("venta", "sale")
    ]:

        registros = extraer_serie(
            evolucion.get(clave),
            municipio,
            tipo,
            id_fotocasa,
            nombre_fotocasa
        )

        todos_los_registros.extend(registros)

        resumen.append({
            "municipio": nombre,
            "tipo": tipo,
            "registros": len(registros),
            "primera_fecha": registros[0]["fecha"],
            "ultima_fecha": registros[-1]["fecha"],
            "precio_ultimo": registros[-1]["precio_eur_m2"]
        })

        print(
            f"{tipo.capitalize()}: {len(registros)} registros | "
            f"{registros[0]['fecha']} - {registros[-1]['fecha']}"
        )


# ============================================================
# COMPROBACIONES
# ============================================================

claves = [
    (r["municipio_codigo"], r["tipo"], r["fecha"])
    for r in todos_los_registros
]

duplicados = len(claves) - len(set(claves))

if duplicados != 0:
    raise ValueError(f"Hay {duplicados} registros duplicados")

total_esperado = len(municipios) * 2 * REGISTROS_ESPERADOS

if len(todos_los_registros) != total_esperado:
    raise ValueError(
        f"Total inesperado: {len(todos_los_registros)}"
    )

if not all(r["precio_eur_m2"] > 0 for r in todos_los_registros):
    raise ValueError("Hay precios no positivos")


# ============================================================
# GUARDAR CSV
# ============================================================

campos = [
    "municipio_codigo",
    "municipio_oficial",
    "fotocasa_id",
    "nombre_fotocasa",
    "tipo",
    "fecha",
    "precio_eur_m2"
]

with open(
    ARCHIVO_CSV,
    "w",
    encoding="utf-8-sig",
    newline=""
) as archivo:

    escritor = csv.DictWriter(
        archivo,
        fieldnames=campos,
        delimiter=";"
    )

    escritor.writeheader()
    escritor.writerows(todos_los_registros)


# ============================================================
# GUARDAR JSON
# ============================================================

resultado_json = {
    "fuente": "Indice Inmobiliario Fotocasa",
    "municipios": len(municipios),
    "registros_totales": len(todos_los_registros),
    "unidad": "euros por metro cuadrado",
    "datos": todos_los_registros
}

with open(
    ARCHIVO_JSON,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        resultado_json,
        archivo,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# RESUMEN
# ============================================================

print("\n" + "=" * 65)
print("RESUMEN DE EXTRACCION")
print("=" * 65)

print("Municipios:", len(municipios))
print("Series:", len(resumen))
print("Registros totales:", len(todos_los_registros))
print("Registros duplicados:", duplicados)

for fila in resumen:
    print(
        f"{fila['municipio']} | {fila['tipo']} | "
        f"{fila['registros']} registros | "
        f"{fila['primera_fecha']} - {fila['ultima_fecha']} | "
        f"Último precio: {fila['precio_ultimo']}"
    )

print("\nARCHIVOS GENERADOS:")
print(ARCHIVO_CSV)
print(ARCHIVO_JSON)

print("\nExtracción terminada.")
