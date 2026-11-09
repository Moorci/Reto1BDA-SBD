
import requests
import json
import os
import sys

# API de Eustat
BASE_URL = "https://www.eustat.eus/bankupx/api/v1/es/DB/"

# Tablas seleccionadas para el reto
TABLAS = {
    "renta_por_edad": "PX_173402_crpf_rpf_rp03.px",
    "renta_por_municipio": "PX_173402_crpf_rpf_rp11s.px",
    "indicadores_municipales": "PX_173402_crpf_rpf_rp36.px",
    "percentiles_renta_municipales": "PX_173402_crpf_rpf_rp30.px",
    "distribucion_renta_municipal": "PX_173402_crpf_rpf_rp31.px",
    "distribucion_renta_por_edad": "PX_173402_crpf_rpf_rp33.px"
}

CARPETA = "originales"

# Permite sobrescribir archivos existentes usando:
# python descargar_datos_eustat.py --sobrescribir
SOBRESCRIBIR = "--sobrescribir" in sys.argv

os.makedirs(CARPETA, exist_ok=True)

sesion = requests.Session()

print("=" * 60)
print("DESCARGA DE DATOS DE EUSTAT")
print("=" * 60)

correctas = 0
errores = 0
omitidas = 0

for nombre, identificador in TABLAS.items():

    print("\n" + "-" * 60)
    print("Tabla:", nombre)
    print("ID:", identificador)

    ruta = os.path.join(CARPETA, f"eustat_{nombre}.json")

    # No sobrescribir archivos existentes por defecto
    if os.path.exists(ruta) and not SOBRESCRIBIR:
        print("OMITIDA: el archivo ya existe.")
        omitidas += 1
        continue

    url = BASE_URL + identificador

    consulta = {
        "query": [],
        "response": {
            "format": "json-stat"
        }
    }

    try:
        respuesta = sesion.post(
            url,
            json=consulta,
            timeout=180
        )

        respuesta.raise_for_status()

        respuesta_json = respuesta.json()

        # Comprobar que la respuesta contiene dataset
        if not isinstance(respuesta_json, dict):
            raise ValueError("La respuesta no es un objeto JSON.")

        if "dataset" not in respuesta_json:
            raise ValueError("La respuesta no contiene la clave dataset.")

        # Obtener los datos de dentro de dataset
        datos = respuesta_json["dataset"]

        # Comprobar estructura JSON-stat
        if not isinstance(datos, dict):
            raise ValueError("El contenido de dataset no es un objeto JSON.")

        if not isinstance(datos.get("value"), list):
            raise ValueError("No se encuentra el listado de valores.")

        if not isinstance(datos.get("dimension"), dict):
            raise ValueError("No se encuentran las dimensiones.")

        valores = datos["value"]

        if len(valores) == 0:
            raise ValueError("La tabla no contiene valores.")

        # Guardar primero en un archivo temporal
        temporal = ruta + ".tmp"

        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump(
                datos,
                archivo,
                ensure_ascii=False,
                indent=2
            )

        # Comprobar que el archivo se puede volver a leer
        with open(temporal, "r", encoding="utf-8") as archivo:
            comprobacion = json.load(archivo)

        if len(comprobacion["value"]) != len(valores):
            raise ValueError("Error al comprobar el archivo guardado.")

        os.replace(temporal, ruta)

        print("DESCARGA CORRECTA")
        print("Archivo:", ruta)
        print("Dimensiones:", len(datos["dimension"]))
        print("Valores almacenados:", len(valores))
        print("Tamaño:", os.path.getsize(ruta), "bytes")

        correctas += 1

    except Exception as error:

        temporal = ruta + ".tmp"

        if os.path.exists(temporal):
            os.remove(temporal)

        print("ERROR:", error)
        errores += 1

sesion.close()

print("\n" + "=" * 60)
print("RESUMEN DE LA DESCARGA")
print("=" * 60)
print("Descargas correctas:", correctas)
print("Errores:", errores)
print("Archivos omitidos:", omitidas)
print("Total de tablas:", len(TABLAS))

if errores > 0:
    print("\nHay descargas pendientes de revisar.")
else:
    print("\nProceso finalizado sin errores.")
