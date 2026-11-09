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

CATALOGO = Path(
    "originales/fotocasa/catalogo_municipios_fotocasa.csv"
)

CARPETA_HTML = Path(
    "originales/fotocasa/masiva"
)

CARPETA_INFORMES = Path(
    "informes/fotocasa"
)

INFORME = (
    CARPETA_INFORMES /
    "localizacion_masiva_fotocasa.csv"
)

PAUSA_SEGUNDOS = 5
TIMEOUT = 30
REGISTROS_ESPERADOS = 82

# Reintentos para errores temporales del servidor.
MAX_INTENTOS = 3
ESPERA_REINTENTO = 15


# ============================================================
# FUNCIONES
# ============================================================

def normalizar(texto):
    texto = str(texto or "").lower().strip()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9]+", " ", texto)

    return " ".join(texto.split())


def generar_slug(nombre):
    """
    Genera un slug inicial a partir del nombre oficial.
    No garantiza que coincida con el slug de Fotocasa.
    """

    return normalizar(nombre).replace(" ", "-")


def buscar_municipio(objeto):

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
            "No se encuentra __initial_props__"
        )

    return json.loads(coincidencia.group(1))


def nombres_coinciden(nombre_oficial, nombre_fotocasa):

    palabras_oficial = sorted(
        normalizar(nombre_oficial).split()
    )

    palabras_fotocasa = sorted(
        normalizar(nombre_fotocasa).split()
    )

    return palabras_oficial == palabras_fotocasa


def consultar_url(sesion, url):

    for intento in range(1, MAX_INTENTOS + 1):

        respuesta = sesion.get(
            url,
            timeout=TIMEOUT
        )

        if respuesta.status_code not in (
            429, 500, 502, 503, 504
        ):
            return respuesta

        if intento < MAX_INTENTOS:

            print(
                f"  Error temporal HTTP {respuesta.status_code}. "
                f"Reintento {intento}/{MAX_INTENTOS - 1}"
            )

            time.sleep(ESPERA_REINTENTO)

    return respuesta


# ============================================================
# PREPARAR CARPETAS Y CATALOGO
# ============================================================

CARPETA_HTML.mkdir(parents=True, exist_ok=True)
CARPETA_INFORMES.mkdir(parents=True, exist_ok=True)

with open(
    CATALOGO,
    encoding="utf-8-sig",
    newline=""
) as archivo:

    lector = csv.DictReader(
        archivo,
        delimiter=";"
    )

    campos_catalogo = lector.fieldnames
    catalogo = list(lector)


pendientes = [
    fila for fila in catalogo
    if fila["estado"] != "validado"
]

print("=" * 70)
print("LOCALIZACION MASIVA DE MUNICIPIOS EN FOTOCASA")
print("=" * 70)

print("Municipios en catálogo:", len(catalogo))
print("Municipios ya validados:", len(catalogo) - len(pendientes))
print("Municipios pendientes:", len(pendientes))

if not pendientes:
    print("\nNo hay municipios pendientes.")
    raise SystemExit


# ============================================================
# CONFIGURAR SESION
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


# ============================================================
# PROCESAR MUNICIPIOS
# ============================================================

campos_informe = [
    "municipio_codigo",
    "municipio_oficial",
    "slug_probado",
    "url",
    "http_status",
    "fotocasa_id",
    "nombre_fotocasa",
    "registros_alquiler",
    "registros_venta",
    "estado",
    "observaciones",
]

resultados_estado = {}

with open(
    INFORME,
    "w",
    encoding="utf-8-sig",
    newline=""
) as archivo:

    escritor = csv.DictWriter(
        archivo,
        fieldnames=campos_informe,
        delimiter=";"
    )

    escritor.writeheader()

    try:

        for numero, registro in enumerate(
            pendientes,
            start=1
        ):

            codigo = registro["municipio_codigo"]
            nombre = registro["municipio_oficial"]

            slug = generar_slug(nombre)

            url = (
                "https://www.fotocasa.es/es/"
                "indice-precio-vivienda/"
                f"alquiler/{slug}/todas-las-zonas"
            )

            resultado = {
                "municipio_codigo": codigo,
                "municipio_oficial": nombre,
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

            print(
                f"\n[{numero}/{len(pendientes)}] {nombre}"
            )

            print("URL:", url)

            try:

                respuesta = consultar_url(
                    sesion,
                    url
                )

                resultado["http_status"] = (
                    respuesta.status_code
                )

                print("HTTP:", respuesta.status_code)

                # Guardar el HTML recibido para poder revisarlo.
                nombre_html = f"{codigo}_{slug}.html"

                ruta_html = CARPETA_HTML / nombre_html

                ruta_html.write_text(
                    respuesta.text,
                    encoding="utf-8"
                )

                if respuesta.status_code != 200:

                    resultado["estado"] = "error_http"

                    resultado["observaciones"] = (
                        f"HTTP {respuesta.status_code}"
                    )

                else:

                    datos = extraer_json(
                        respuesta.text
                    )

                    municipio = buscar_municipio(
                        datos
                    )

                    if municipio is None:

                        resultado["estado"] = (
                            "sin_municipality"
                        )

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

                        alquiler = evolucion.get(
                            "rent", []
                        )

                        venta = evolucion.get(
                            "sale", []
                        )

                        if not isinstance(alquiler, list):
                            alquiler = []

                        if not isinstance(venta, list):
                            venta = []

                        resultado["registros_alquiler"] = len(
                            alquiler
                        )

                        resultado["registros_venta"] = len(
                            venta
                        )

                        coincide = nombres_coinciden(
                            nombre,
                            resultado["nombre_fotocasa"]
                        )

                        series_correctas = (
                            len(alquiler) == REGISTROS_ESPERADOS
                            and
                            len(venta) == REGISTROS_ESPERADOS
                        )

                        if (
                            resultado["fotocasa_id"]
                            and coincide
                            and series_correctas
                        ):

                            resultado["estado"] = (
                                "candidato_valido"
                            )

                        else:

                            resultado["estado"] = (
                                "revision_manual"
                            )

                            resultado["observaciones"] = (
                                f"Nombre coincidente: {coincide}. "
                                f"Series correctas: {series_correctas}."
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
                            "Alquiler:",
                            resultado["registros_alquiler"]
                        )

                        print(
                            "Venta:",
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

                print("ERROR DE EXTRACCION:", error)

            except Exception as error:

                resultado["estado"] = "error"
                resultado["observaciones"] = str(error)

                print("ERROR:", error)

            # Guardar cada resultado inmediatamente.
            escritor.writerow(resultado)
            archivo.flush()

            estado = resultado["estado"]

            resultados_estado[estado] = (
                resultados_estado.get(estado, 0) + 1
            )

            # Pausa entre peticiones.
            if numero < len(pendientes):
                time.sleep(PAUSA_SEGUNDOS)

    except KeyboardInterrupt:

        print(
            "\nProceso interrumpido manualmente. "
            "Los resultados anteriores están guardados."
        )

    finally:

        sesion.close()


# ============================================================
# RESUMEN
# ============================================================

print("\n" + "=" * 70)
print("RESUMEN DE LOCALIZACION MASIVA")
print("=" * 70)

for estado, cantidad in sorted(
    resultados_estado.items()
):

    print(f"{estado}: {cantidad}")

print(
    "\nMunicipios procesados:",
    sum(resultados_estado.values())
)

print("Municipios pendientes de procesar:",
      len(pendientes) - sum(resultados_estado.values()))

print("\nInforme generado:")
print(INFORME)

print("\nHTML guardados en:")
print(CARPETA_HTML)

print("\nEl catálogo principal NO se ha modificado.")