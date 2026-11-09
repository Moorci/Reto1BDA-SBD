
import json
import os

CARPETA = "originales"

ARCHIVOS = [
    "eustat_renta_por_edad.json",
    "eustat_renta_por_municipio.json",
    "eustat_indicadores_municipales.json",
    "eustat_percentiles_renta_municipales.json",
    "eustat_distribucion_renta_municipal.json",
    "eustat_distribucion_renta_por_edad.json"
]

for nombre in ARCHIVOS:

    ruta = os.path.join(CARPETA, nombre)

    with open(ruta, "r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    dimensiones = datos["dimension"]

    print("\n" + "=" * 70)
    print(nombre)
    print("=" * 70)

    print("Orden de dimensiones:", dimensiones["id"])
    print("Tamaño de dimensiones:", dimensiones["size"])

    for nombre_dimension in dimensiones["id"]:

        contenido = dimensiones[nombre_dimension]
        categoria = contenido["category"]

        etiquetas = categoria["label"]

        print("\nDIMENSIÓN:", nombre_dimension)
        print("Categorías:", len(etiquetas))

        # Mostrar todas las categorías de años y edades
        if nombre_dimension in ["periodo", "edad"]:
            for codigo, etiqueta in etiquetas.items():
                print(codigo, ":", etiqueta)

        # Mostrar una muestra de los territorios
        elif nombre_dimension in [
            "ámbitos territoriales",
            "territorio historico"
        ]:
            for codigo, etiqueta in list(etiquetas.items())[:15]:
                print(codigo, ":", etiqueta)

        # Mostrar todas las categorías del resto
        else:
            for codigo, etiqueta in etiquetas.items():
                print(codigo, ":", etiqueta)
