
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

print("=" * 60)
print("VALIDACIÓN DE DATOS DE EUSTAT")
print("=" * 60)

errores = 0

for nombre in ARCHIVOS:

    ruta = os.path.join(CARPETA, nombre)

    print("\n" + "-" * 60)
    print("Archivo:", nombre)

    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        dimensiones = datos.get("dimension")
        valores = datos.get("value")

        if not isinstance(dimensiones, dict):
            raise ValueError("Dimensiones incorrectas.")

        if not isinstance(valores, list):
            raise ValueError("Valores incorrectos.")

        if len(valores) == 0:
            raise ValueError("No hay registros.")

        print("VALIDACIÓN GENERAL CORRECTA")
        print("Dimensiones:", len(dimensiones))
        print("Registros:", len(valores))
        print("Valores no nulos:", sum(v is not None for v in valores))
        print("Tamaño:", os.path.getsize(ruta), "bytes")

        # Comprobaciones adicionales del archivo de percentiles
        if nombre == "eustat_percentiles_renta_municipales.json":

            print("\nComprobaciones específicas de percentiles:")

            tamanos = dimensiones.get("size")

            if tamanos != [276, 12, 3, 12]:
                raise ValueError(
                    f"Tamaños de dimensiones incorrectos: {tamanos}"
                )

            if len(valores) != 119232:
                raise ValueError(
                    f"Número de valores incorrecto: {len(valores)}"
                )

            print("Dimensiones esperadas:", tamanos)
            print("Número de valores esperado: 119232")

            # Recuperar las posiciones de las categorías
            def obtener_posicion(nombre_dimension, codigo):
                categoria = dimensiones[nombre_dimension]["category"]
                indices = categoria["index"]

                if isinstance(indices, list):
                    return indices.index(codigo)

                if isinstance(indices, dict):
                    return int(indices[codigo])

                raise ValueError("Formato de índices desconocido.")

            i_ambito = obtener_posicion(
                "ámbitos territoriales", "00001"
            )
            i_percentil = obtener_posicion(
                "percentil (renta personal)", "20"
            )
            i_sexo = obtener_posicion("sexo", "10")
            i_periodo = obtener_posicion("periodo", "2024")

            # Calcular la posición del dato en el array
            indice = (
                ((i_ambito * 12 + i_percentil) * 3 + i_sexo) * 12
                + i_periodo
            )

            valor_prueba = valores[indice]

            print("Valor de prueba:", valor_prueba)

            if valor_prueba != 5687:
                raise ValueError(
                    f"El valor de prueba debería ser 5687, "
                    f"pero se ha encontrado {valor_prueba}."
                )

            print("COMPROBACIÓN DE PERCENTILES CORRECTA")

    except Exception as error:
        errores += 1
        print("ERROR:", error)

print("\n" + "=" * 60)
print("RESUMEN DE VALIDACIÓN")
print("=" * 60)

print("Archivos revisados:", len(ARCHIVOS))
print("Archivos con errores:", errores)

if errores == 0:
    print("TODOS LOS ARCHIVOS HAN SUPERADO LA VALIDACIÓN.")
else:
    print("HAY ARCHIVOS QUE NECESITAN REVISIÓN.")
