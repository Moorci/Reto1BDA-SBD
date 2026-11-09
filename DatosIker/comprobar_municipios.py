
import json
import os

# Archivos de Eustat y EMAL
archivo_eustat = os.path.join(
    "originales",
    "eustat_renta_por_municipio.json"
)

archivos_emal = [
    os.path.join("procesados", "emal_alquiler_anual_municipios.json"),
    os.path.join("procesados", "emal_alquiler_vigente_municipios.json")
]

# Cargar códigos territoriales de Eustat
with open(archivo_eustat, "r", encoding="utf-8") as f:
    datos = json.load(f)

territorios = datos["dimension"]["ámbitos territoriales"]["category"]["label"]

codigos_eustat = set(territorios.keys())

print("=" * 65)
print("COMPROBACIÓN DE CÓDIGOS MUNICIPALES")
print("=" * 65)

for ruta in archivos_emal:

    print("\nArchivo:", ruta)

    with open(ruta, "r", encoding="utf-8") as f:
        registros = json.load(f)

    codigos_emal = {
        str(r["municipio_codigo"]).zfill(5)
        for r in registros
    }

    coincidentes = codigos_eustat.intersection(codigos_emal)
    exclusivos_emal = codigos_emal - codigos_eustat
    exclusivos_eustat = codigos_eustat - codigos_emal

    print("Registros EMAL:", len(registros))
    print("Códigos distintos en EMAL:", len(codigos_emal))
    print("Códigos coincidentes:", len(coincidentes))
    print("Códigos de EMAL sin coincidencia:", len(exclusivos_emal))

    if exclusivos_emal:
        print("Ejemplos sin coincidencia:", sorted(exclusivos_emal)[:10])

    print("\nEjemplos de municipios coincidentes:")

    for codigo in sorted(coincidentes)[:10]:
        print(codigo, "-", territorios[codigo])

    print("\nAlgunos territorios de Eustat sin coincidencia:")
    for codigo in sorted(exclusivos_eustat)[:10]:
        print(codigo, "-", territorios[codigo])

print("\nComprobación finalizada.")
