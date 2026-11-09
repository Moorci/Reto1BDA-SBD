
import csv
import json
from pathlib import Path
from collections import defaultdict

# ============================================================
# CONFIGURACION
# ============================================================

CARPETA = Path("procesados/fotocasa")

ARCHIVO_BILBAO = CARPETA / "bilbao_precios.csv"
ARCHIVO_PILOTO = CARPETA / "series_historicas_piloto.csv"
ARCHIVO_COMPLEMENTO = CARPETA / "series_historicas_complemento.csv"

ARCHIVO_SALIDA_CSV = CARPETA / "series_historicas_10_municipios.csv"
ARCHIVO_SALIDA_JSON = CARPETA / "series_historicas_10_municipios.json"

REGISTROS_POR_SERIE = 82
MUNICIPIOS_ESPERADOS = 10

CAMPOS = [
    "municipio_codigo",
    "municipio_oficial",
    "fotocasa_id",
    "nombre_fotocasa",
    "tipo",
    "fecha",
    "precio_eur_m2"
]


# ============================================================
# FUNCIONES
# ============================================================

def convertir_precio(valor):
    texto = str(valor).strip()

    # Admitir coma decimal o punto decimal.
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")

    precio = float(texto)

    if precio <= 0:
        raise ValueError(f"Precio no positivo: {valor}")

    return precio


def leer_csv_normalizado(archivo):
    with open(
        archivo,
        encoding="utf-8-sig",
        newline=""
    ) as f:

        return list(csv.DictReader(f, delimiter=";"))


# ============================================================
# LEER LOS NUEVE MUNICIPIOS
# ============================================================

print("=" * 65)
print("CONSOLIDACION DE SERIES HISTORICAS FOTOCASA")
print("=" * 65)

registros = []

for archivo in [ARCHIVO_PILOTO, ARCHIVO_COMPLEMENTO]:

    if not archivo.exists():
        raise FileNotFoundError(archivo)

    datos = leer_csv_normalizado(archivo)

    print(f"\nArchivo: {archivo}")
    print("Registros leídos:", len(datos))

    for fila in datos:

        registro = {
            "municipio_codigo": fila["municipio_codigo"],
            "municipio_oficial": fila["municipio_oficial"],
            "fotocasa_id": fila["fotocasa_id"],
            "nombre_fotocasa": fila["nombre_fotocasa"],
            "tipo": fila["tipo"],
            "fecha": fila["fecha"],
            "precio_eur_m2": convertir_precio(
                fila["precio_eur_m2"]
            )
        }

        registros.append(registro)


# ============================================================
# NORMALIZAR BILBAO
# ============================================================

if not ARCHIVO_BILBAO.exists():
    raise FileNotFoundError(ARCHIVO_BILBAO)

with open(
    ARCHIVO_BILBAO,
    encoding="utf-8-sig",
    newline=""
) as f:

    datos_bilbao = list(
        csv.DictReader(f, delimiter=",")
    )

print(f"\nArchivo: {ARCHIVO_BILBAO}")
print("Registros leídos:", len(datos_bilbao))

for fila in datos_bilbao:

    if fila["municipio_codigo"] != "48020":
        raise ValueError(
            f"Código inesperado en Bilbao: "
            f"{fila['municipio_codigo']}"
        )

    tipo = fila["tipo_operacion"]

    if tipo not in ["alquiler", "venta"]:
        raise ValueError(
            f"Tipo de operación desconocido: {tipo}"
        )

    registro = {
        "municipio_codigo": "48020",
        "municipio_oficial": "Bilbao",
        "fotocasa_id": "48020",
        "nombre_fotocasa": "Bilbao",
        "tipo": tipo,
        "fecha": fila["fecha"],
        "precio_eur_m2": convertir_precio(
            fila["precio_m2"]
        )
    }

    registros.append(registro)


# ============================================================
# ORDENAR REGISTROS
# ============================================================

registros.sort(
    key=lambda r: (
        r["municipio_codigo"],
        r["tipo"],
        r["fecha"]
    )
)


# ============================================================
# VALIDACIONES GENERALES
# ============================================================

municipios = set(
    r["municipio_codigo"] for r in registros
)

if len(municipios) != MUNICIPIOS_ESPERADOS:
    raise ValueError(
        f"Se esperaban {MUNICIPIOS_ESPERADOS} municipios "
        f"y hay {len(municipios)}"
    )

# Comprobar duplicados.
claves = [
    (
        r["municipio_codigo"],
        r["tipo"],
        r["fecha"]
    )
    for r in registros
]

duplicados = len(claves) - len(set(claves))

if duplicados != 0:
    raise ValueError(
        f"Se han encontrado {duplicados} duplicados"
    )

# Comprobar precios.
if not all(
    r["precio_eur_m2"] > 0
    for r in registros
):
    raise ValueError("Hay precios no positivos")

# Agrupar por municipio y tipo.
grupos = defaultdict(list)

for r in registros:
    grupos[
        (r["municipio_codigo"], r["tipo"])
    ].append(r)

if len(grupos) != 20:
    raise ValueError(
        f"Se esperaban 20 series y hay {len(grupos)}"
    )

for clave, serie in grupos.items():

    if len(serie) != REGISTROS_POR_SERIE:
        raise ValueError(
            f"Serie {clave}: se esperaban "
            f"{REGISTROS_POR_SERIE} registros "
            f"y hay {len(serie)}"
        )

    fechas = [r["fecha"] for r in serie]

    if len(set(fechas)) != REGISTROS_POR_SERIE:
        raise ValueError(
            f"Fechas duplicadas en la serie {clave}"
        )

    if fechas[0] != "2020-01" or fechas[-1] != "2026-10":
        raise ValueError(
            f"Periodo incorrecto en {clave}: "
            f"{fechas[0]} - {fechas[-1]}"
        )

total_esperado = (
    MUNICIPIOS_ESPERADOS *
    2 *
    REGISTROS_POR_SERIE
)

if len(registros) != total_esperado:
    raise ValueError(
        f"Total inesperado: {len(registros)}"
    )


# ============================================================
# GUARDAR CSV
# ============================================================

with open(
    ARCHIVO_SALIDA_CSV,
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    escritor = csv.DictWriter(
        f,
        fieldnames=CAMPOS,
        delimiter=";"
    )

    escritor.writeheader()
    escritor.writerows(registros)


# ============================================================
# GUARDAR JSON
# ============================================================

resultado = {
    "fuente": "Indice Inmobiliario Fotocasa",
    "municipios": len(municipios),
    "series": len(grupos),
    "registros_totales": len(registros),
    "periodo": {
        "inicio": "2020-01",
        "fin": "2026-10"
    },
    "unidad": "euros por metro cuadrado",
    "datos": registros
}

with open(
    ARCHIVO_SALIDA_JSON,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        resultado,
        f,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# RESUMEN FINAL
# ============================================================

print("\n" + "=" * 65)
print("RESUMEN DE CONSOLIDACION")
print("=" * 65)

print("Municipios:", len(municipios))
print("Series:", len(grupos))
print("Registros totales:", len(registros))
print("Registros duplicados:", duplicados)

print("\nDETALLE POR MUNICIPIO Y TIPO:")

for codigo, tipo in sorted(grupos):

    serie = grupos[(codigo, tipo)]

    print(
        f"{serie[0]['municipio_oficial']} | "
        f"{tipo} | "
        f"{len(serie)} registros | "
        f"{serie[0]['fecha']} - {serie[-1]['fecha']}"
    )

print("\nARCHIVOS GENERADOS:")
print(ARCHIVO_SALIDA_CSV)
print(ARCHIVO_SALIDA_JSON)

print("\nConsolidacion terminada correctamente.")
