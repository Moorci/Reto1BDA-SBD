import requests
import json

URL = "https://www.eustat.eus/bankupx/api/v1/es/DB/PX_173402_crpf_rpf_rp30.px"

# Leer los metadatos de la tabla
with open(
    "originales/metadatos_percentiles_renta_municipales.json",
    "r",
    encoding="utf-8"
) as archivo:
    metadatos = json.load(archivo)

variables = metadatos["variables"]

# Obtener los códigos de cada variable
valores = {
    variable["code"]: variable["values"]
    for variable in variables
}

# Seleccionar los primeros cinco ámbitos
ambitos = valores["ámbitos territoriales"][:5]

consulta = {
    "query": [
        {
            "code": "ámbitos territoriales",
            "selection": {
                "filter": "item",
                "values": ambitos
            }
        },
        {
            "code": "percentil (renta personal)",
            "selection": {
                "filter": "item",
                "values": valores["percentil (renta personal)"]
            }
        },
        {
            "code": "sexo",
            "selection": {
                "filter": "item",
                "values": valores["sexo"]
            }
        },
        {
            "code": "periodo",
            "selection": {
                "filter": "item",
                "values": valores["periodo"]
            }
        }
    ],
    "response": {
        "format": "json-stat"
    }
}

print("Ámbitos seleccionados:", ambitos)

respuesta = requests.post(
    URL,
    json=consulta,
    headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    },
    timeout=180
)

print("Estado HTTP:", respuesta.status_code)

respuesta.raise_for_status()

resultado = respuesta.json()["dataset"]

print("Dimensiones:", len(resultado["dimension"]))
print("Valores recibidos:", len(resultado["value"]))
print("Tamaño del archivo no comprimido:", len(respuesta.content), "bytes")

print("\nESTRUCTURA DEL JSON-STAT")
print("Claves:", list(resultado.keys()))

print("\nCONTENIDO DE DIMENSION:")
for nombre, dimension in resultado["dimension"].items():

    # Ignorar elementos auxiliares que no sean diccionarios
    if not isinstance(dimension, dict):
        print(nombre, "- elemento auxiliar:", type(dimension).__name__)
        continue

    categorias = dimension.get("category", {}).get("label", {})

    print(
        nombre,
        "- categorías:",
        len(categorias),
        "- primeros valores:",
        list(categorias.values())[:5]
    )

print("\nPRUEBA FINALIZADA")