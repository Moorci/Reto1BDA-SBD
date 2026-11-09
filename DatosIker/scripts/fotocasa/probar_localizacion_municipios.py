
import csv
import json
import re
import time
import unicodedata
from pathlib import Path

import requests


# ============================================================
# CONFIGURACION
# ============================================================

CARPETA = Path("originales/fotocasa")
CARPETA_HTML = CARPETA / "pruebas"
CARPETA_INFORMES = Path("informes/fotocasa")

ARCHIVO_CATALOGO = CARPETA / "catalogo_municipios_fotocasa.csv"

ARCHIVO_RESULTADO = (
    CARPETA_INFORMES / "prueba_localizacion_municipios.csv"
)

PAUSA_SEGUNDOS = 5
TIMEOUT = 30

# Cinco municipios para la prueba inicial.
MUNICIPIOS_PRUEBA = {
    "48001": "abadino",
    "20001": "abaltzisketa",
    "48002": "abanto-y-ciervana-abanto-zierbena",
    "20002": "aduna",
    "01051": "salvatierra-agurain",
}


# ============================================================
# FUNCIONES
# ============================================================

def normalizar(texto):
    """Normaliza texto para facilitar las comparaciones."""

    texto = str(texto or "").lower().strip()

    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9]+", " ", texto)

    return " ".join(texto.split())


def buscar_municipio(objeto):
    """Busca recursivamente el objeto municipality."""

    if isinstance(objeto, dict):

        if (
            "priceEvolution" in objeto
            and "id" in objeto
        ):
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


def extraer_json(html):
    """Extrae el JSON de __initial_props__."""

    patron = (
        r'<script\b(?=[^>]*\bid=["\']__initial_props__["\'])'
        r'[^>]*>(.*?)</script>'
    )

    coincidencia = re.search(
        patron,
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    if not coincidencia:
        raise ValueError(
            "No se encuentra el JSON __initial_props__"
        )

    return json.loads(coincidencia.group(1))


def guardar_html(nombre_archivo, contenido):
    CARPETA_HTML.mkdir(parents=True, exist_ok=True)

    ruta = CARPETA_HTML / nombre_archivo

    ruta.write_text(
        contenido,
        encoding="utf-8"
    )

    return ruta


# ============================================================
# PREPARAR CARPETAS Y CATALOGO
# ============================================================

CARPETA_HTML.mkdir(parents=True, exist_ok=True)
CARPETA_INFORMES.mkdir(parents=True, exist_ok=True)

with open(
    ARCHIVO_CATALOGO,
    encoding="utf-8-sig",
    newline=""
) as archivo:

    lector = csv.DictReader(archivo, delimiter=";")
    catalogo = list(lector)


# ============================================================
# CONSULTAR FOTOCASA
# ============================================================

sesion = requests.Session()

sesion.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
})

resultados = []

print("=" * 65)
print("PRUEBA DE LOCALIZACION DE MUNICIPIOS EN FOTOCASA")
print("=" * 65)

for numero, (codigo, slug) in enumerate(
    MUNICIPIOS_PRUEBA.items(),
    start=1
):

    registro = next(
        (
            fila for fila in catalogo
            if fila["municipio_codigo"] == codigo
        ),
        None
    )

    if registro is None:
        print(f"\n[{numero}] ERROR: codigo {codigo} no encontrado")
        continue

    nombre_oficial = registro["municipio_oficial"]

    url = (
        "https://www.fotocasa.es/es/indice-precio-vivienda/"
        f"alquiler/{slug}/todas-las-zonas"
    )

    resultado = {
        "municipio_codigo": codigo,
        "municipio_oficial": nombre_oficial,
        "slug_probado": slug,
        "url": url,
        "http_status": "",
        "fotocasa_id": "",
        "nombre_fotocasa": "",
        "registros_alquiler": 0,
        "registros_venta": 0,
        "estado": "pendiente_revision",
        "observaciones": "",
    }

    print(f"\n[{numero}/5] {nombre_oficial}")
    print("URL:", url)

    try:

        respuesta = sesion.get(
            url,
            timeout=TIMEOUT
        )

        resultado["http_status"] = respuesta.status_code

        print("HTTP:", respuesta.status_code)

        nombre_html = f"{codigo}_{slug}.html"

        guardar_html(
            nombre_html,
            respuesta.text
        )

        if respuesta.status_code != 200:

            resultado["estado"] = "error_http"
            resultado["observaciones"] = (
                f"Respuesta HTTP {respuesta.status_code}"
            )

        else:

            datos = extraer_json(respuesta.text)

            municipio = buscar_municipio(datos)

            if municipio is None:

                resultado["estado"] = "sin_municipality"
                resultado["observaciones"] = (
                    "No se encuentra el objeto municipality"
                )

            else:

                resultado["fotocasa_id"] = str(
                    municipio.get("id", "")
                )

                resultado["nombre_fotocasa"] = str(
                    municipio.get("name", "")
                )

                evolucion = municipio.get(
                    "priceEvolution", {}
                )

                alquiler = evolucion.get("rent", [])
                venta = evolucion.get("sale", [])

                resultado["registros_alquiler"] = len(
                    alquiler if isinstance(alquiler, list) else []
                )

                resultado["registros_venta"] = len(
                    venta if isinstance(venta, list) else []
                )

                nombre_coincide = (
                    sorted(normalizar(nombre_oficial).split())
                    == sorted(normalizar(resultado["nombre_fotocasa"]).split())
                )

                if (
                    resultado["fotocasa_id"]
                    and nombre_coincide
                    and resultado["registros_alquiler"] > 0
                    and resultado["registros_venta"] > 0
                ):

                    resultado["estado"] = "candidato_valido"

                else:

                    resultado["estado"] = "revision_manual"

                    resultado["observaciones"] = (
                        f"Nombre coincidente: {nombre_coincide}. "
                        "Revisar identificador y series."
                    )

                print(
                    "ID Fotocasa:",
                    resultado["fotocasa_id"]
                )

                print(
                    "Nombre Fotocasa:",
                    resultado["nombre_fotocasa"]
                )

                print(
                    "Registros alquiler:",
                    resultado["registros_alquiler"]
                )

                print(
                    "Registros venta:",
                    resultado["registros_venta"]
                )

                print(
                    "Estado:",
                    resultado["estado"]
                )

    except requests.RequestException as error:

        resultado["estado"] = "error_conexion"
        resultado["observaciones"] = str(error)

        print("ERROR DE CONEXION:", error)

    except (ValueError, json.JSONDecodeError) as error:

        resultado["estado"] = "error_extraccion"
        resultado["observaciones"] = str(error)

        print("ERROR AL EXTRAER DATOS:", error)

    except Exception as error:

        resultado["estado"] = "error"
        resultado["observaciones"] = str(error)

        print("ERROR:", error)

    resultados.append(resultado)

    # Pausa entre peticiones para reducir la carga.
    if numero < len(MUNICIPIOS_PRUEBA):
        time.sleep(PAUSA_SEGUNDOS)


# ============================================================
# GUARDAR INFORME
# ============================================================

campos = list(resultados[0].keys()) if resultados else []

with open(
    ARCHIVO_RESULTADO,
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
    escritor.writerows(resultados)


# ============================================================
# RESUMEN
# ============================================================

print("\n" + "=" * 65)
print("RESUMEN DE LA PRUEBA")
print("=" * 65)

for estado in sorted(
    set(r["estado"] for r in resultados)
):
    cantidad = sum(
        r["estado"] == estado
        for r in resultados
    )

    print(f"{estado}: {cantidad}")

print("\nMunicipios consultados:", len(resultados))

print("\nInforme generado:")
print(ARCHIVO_RESULTADO)

print("\nHTML guardados en:")
print(CARPETA_HTML)

print("\nEl catalogo principal no se ha modificado.")
