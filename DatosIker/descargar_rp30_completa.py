import requests
import json
import os
import time

URL = (
    "https://www.eustat.eus/bankupx/api/v1/es/DB/"
    "PX_173402_crpf_rpf_rp30.px"
)

ARCHIVO_METADATOS = (
    "originales/metadatos_percentiles_renta_municipales.json"
)

ARCHIVO_FINAL = (
    "originales/eustat_percentiles_renta_municipales.json"
)

TAMANO_BLOQUE = 5

# Leer los metadatos
with open(ARCHIVO_METADATOS, "r", encoding="utf-8") as archivo:
    metadatos = json.load(archivo)

variables = {
    variable["code"]: variable["values"]
    for variable in metadatos["variables"]
}

ambitos = variables["ámbitos territoriales"]
percentiles = variables["percentil (renta personal)"]
sexos = variables["sexo"]
periodos = variables["periodo"]

print("=" * 60)
print("DESCARGA COMPLETA DE PERCENTILES DE RENTA")
print("=" * 60)

print("Ámbitos:", len(ambitos))
print("Percentiles:", len(percentiles))
print("Sexos:", len(sexos))
print("Periodos:", len(periodos))

total_esperado = (
    len(ambitos) *
    len(percentiles) *
    len(sexos) *
    len(periodos)
)

print("Valores esperados:", total_esperado)

sesion = requests.Session()

sesion.headers.update({
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
})

resultado_final = None
valores_totales = []
etiquetas_ambitos = {}
indice_ambitos = {}

try:

    # Recorrer los ámbitos en bloques
    for inicio in range(0, len(ambitos), TAMANO_BLOQUE):

        bloque = ambitos[inicio:inicio + TAMANO_BLOQUE]

        print(
            f"\nDescargando ámbitos "
            f"{inicio + 1}-{inicio + len(bloque)} "
            f"de {len(ambitos)}"
        )

        consulta = {
            "query": [
                {
                    "code": "ámbitos territoriales",
                    "selection": {
                        "filter": "item",
                        "values": bloque
                    }
                },
                {
                    "code": "percentil (renta personal)",
                    "selection": {
                        "filter": "item",
                        "values": percentiles
                    }
                },
                {
                    "code": "sexo",
                    "selection": {
                        "filter": "item",
                        "values": sexos
                    }
                },
                {
                    "code": "periodo",
                    "selection": {
                        "filter": "item",
                        "values": periodos
                    }
                }
            ],
            "response": {
                "format": "json-stat"
            }
        }

        respuesta = sesion.post(
            URL,
            json=consulta,
            timeout=180
        )

        respuesta.raise_for_status()

        respuesta_json = respuesta.json()

        if "dataset" not in respuesta_json:
            raise ValueError("La respuesta no contiene dataset.")

        datos = respuesta_json["dataset"]

        if not isinstance(datos.get("value"), list):
            raise ValueError("No se encuentra la lista de valores.")

        valores = datos["value"]

        # Comprobar el número de valores del bloque
        esperados_bloque = (
            len(bloque) *
            len(percentiles) *
            len(sexos) *
            len(periodos)
        )

        if len(valores) != esperados_bloque:
            raise ValueError(
                f"Bloque incorrecto: esperados "
                f"{esperados_bloque}, recibidos {len(valores)}."
            )

        # Guardar la estructura de la primera respuesta
        if resultado_final is None:

            resultado_final = datos.copy()

            resultado_final["dimension"] = (
                json.loads(json.dumps(datos["dimension"]))
            )

            # Preparar los campos que pueden contener
            # información correspondiente a cada valor
            campos_por_valor = {}

            for clave, contenido in datos.items():
                if (
                    clave not in ("dimension", "value")
                    and isinstance(contenido, list)
                    and len(contenido) == len(valores)
                ):
                    campos_por_valor[clave] = []

        # Acumular los valores
        valores_totales.extend(valores)

        # Acumular las etiquetas y los índices de los ámbitos
        dimension_ambitos = datos["dimension"][
            "ámbitos territoriales"
        ]

        categoria = dimension_ambitos["category"]

        for codigo in bloque:

            if codigo not in categoria["label"]:
                raise ValueError(
                    f"No se encuentra la etiqueta del ámbito {codigo}."
                )

            if codigo not in categoria["index"]:
                raise ValueError(
                    f"No se encuentra el índice del ámbito {codigo}."
                )

            if codigo in etiquetas_ambitos:
                raise ValueError(
                    f"Ámbito duplicado: {codigo}"
                )

            etiquetas_ambitos[codigo] = categoria["label"][codigo]
            indice_ambitos[codigo] = len(indice_ambitos)

        # Acumular posibles campos asociados a cada valor
        for clave in campos_por_valor:
            campos_por_valor[clave].extend(datos[clave])

        print("Valores recibidos:", len(valores))

        time.sleep(0.5)

    # Comprobar el total de valores
    if len(valores_totales) != total_esperado:
        raise ValueError(
            f"Total incorrecto: esperados {total_esperado}, "
            f"recibidos {len(valores_totales)}."
        )

    # Reconstruir la dimensión de ámbitos territoriales
    dimension = resultado_final["dimension"]["ámbitos territoriales"]

    dimension["category"]["index"] = indice_ambitos
    dimension["category"]["label"] = etiquetas_ambitos

    # Actualizar el tamaño de las dimensiones
    resultado_final["dimension"]["size"][0] = len(ambitos)

    # Guardar todos los valores
    resultado_final["value"] = valores_totales

    # Guardar otros campos asociados a cada valor, si existen
    for clave, contenido in campos_por_valor.items():
        resultado_final[clave] = contenido

    # Comprobar que están todos los ámbitos
    if len(etiquetas_ambitos) != len(ambitos):
        raise ValueError("Faltan ámbitos territoriales.")

    # Guardar temporalmente
    temporal = ARCHIVO_FINAL + ".tmp"

    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(
            resultado_final,
            archivo,
            ensure_ascii=False,
            indent=2
        )

    # Comprobar el archivo guardado
    with open(temporal, "r", encoding="utf-8") as archivo:
        comprobacion = json.load(archivo)

    if len(comprobacion["value"]) != total_esperado:
        raise ValueError("Error al comprobar el archivo final.")

    os.replace(temporal, ARCHIVO_FINAL)

    print("\n" + "=" * 60)
    print("DESCARGA COMPLETADA")
    print("=" * 60)
    print("Archivo:", ARCHIVO_FINAL)
    print("Ámbitos:", len(etiquetas_ambitos))
    print("Dimensiones:", len(resultado_final["dimension"]))
    print("Valores:", len(valores_totales))
    print("Valores nulos:", sum(v is None for v in valores_totales))
    print("Tamaño:", os.path.getsize(ARCHIVO_FINAL), "bytes")

except Exception as error:

    temporal = ARCHIVO_FINAL + ".tmp"

    if os.path.exists(temporal):
        os.remove(temporal)

    print("\nERROR:", error)
    print("No se ha completado la descarga.")

finally:
    sesion.close()