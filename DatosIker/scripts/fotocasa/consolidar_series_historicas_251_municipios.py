
import csv
import json
from pathlib import Path
from collections import defaultdict

# ============================================================
# CONFIGURACION
# ============================================================

BASE = Path(__file__).resolve().parents[2]

CARPETA = BASE / "procesados" / "fotocasa"
CARPETA_INFORMES = BASE / "informes" / "fotocasa"

ARCHIVOS_ENTRADA = [
    CARPETA / "series_historicas_10_municipios.csv",
    CARPETA / "series_historicas_241_municipios.csv"
]

ARCHIVO_SALIDA_CSV = (
    CARPETA / "series_historicas_251_municipios.csv"
)

ARCHIVO_SALIDA_JSON = (
    CARPETA / "series_historicas_251_municipios.json"
)

ARCHIVO_INFORME = (
    CARPETA_INFORMES / "validacion_series_251_municipios.csv"
)

MUNICIPIOS_ESPERADOS = 251
REGISTROS_POR_SERIE = 82

TIPOS_ESPERADOS = {"alquiler", "venta"}

CAMPOS = [
    "municipio_codigo",
    "municipio_oficial",
    "fotocasa_id",
    "nombre_fotocasa",
    "tipo",
    "fecha",
    "precio_eur_m2"
]

MESES_ESPERADOS = [
    f"{anio}-{mes:02d}"
    for anio in range(2020, 2027)
    for mes in range(1, 13)
    if (anio, mes) <= (2026, 10)
]


# ============================================================
# LECTURA Y NORMALIZACION
# ============================================================

def leer_csv(archivo):

    if not archivo.exists():
        raise FileNotFoundError(archivo)

    with open(
        archivo,
        encoding="utf-8-sig",
        newline=""
    ) as f:

        lector = csv.DictReader(f, delimiter=";")

        if lector.fieldnames != CAMPOS:
            raise ValueError(
                f"Cabeceras incorrectas en {archivo.name}: "
                f"{lector.fieldnames}"
            )

        return list(lector)


def convertir_registro(fila, archivo):

    codigo = fila["municipio_codigo"].strip()
    tipo = fila["tipo"].strip()
    fecha = fila["fecha"].strip()

    if len(codigo) != 5 or not codigo.isdigit():
        raise ValueError(
            f"Código municipal incorrecto en {archivo}: {codigo}"
        )

    if tipo not in TIPOS_ESPERADOS:
        raise ValueError(
            f"Tipo incorrecto en {archivo}: {tipo}"
        )

    if fecha not in MESES_ESPERADOS:
        raise ValueError(
            f"Fecha incorrecta en {archivo}: {fecha}"
        )

    precio = float(fila["precio_eur_m2"])

    if precio <= 0:
        raise ValueError(
            f"Precio no positivo en {archivo}: {precio}"
        )

    return {
        "municipio_codigo": codigo,
        "municipio_oficial": fila["municipio_oficial"].strip(),
        "fotocasa_id": fila["fotocasa_id"].strip(),
        "nombre_fotocasa": fila["nombre_fotocasa"].strip(),
        "tipo": tipo,
        "fecha": fecha,
        "precio_eur_m2": precio
    }


# ============================================================
# CONSOLIDACION
# ============================================================

print("=" * 65)
print("CONSOLIDACION HISTORICA FOTOCASA - 251 MUNICIPIOS")
print("=" * 65)

registros = []

for archivo in ARCHIVOS_ENTRADA:

    datos = leer_csv(archivo)

    print(f"\nArchivo: {archivo.name}")
    print("Registros leidos:", len(datos))

    for fila in datos:
        registros.append(
            convertir_registro(fila, archivo.name)
        )

print("\nTotal de registros leidos:", len(registros))


# ============================================================
# VALIDACIONES
# ============================================================

municipios = {
    r["municipio_codigo"]
    for r in registros
}

if len(municipios) != MUNICIPIOS_ESPERADOS:
    raise ValueError(
        f"Se esperaban {MUNICIPIOS_ESPERADOS} municipios "
        f"y hay {len(municipios)}."
    )

# Comprobar que cada municipio tiene un unico ID Fotocasa.
ids_por_municipio = defaultdict(set)

for r in registros:
    ids_por_municipio[r["municipio_codigo"]].add(
        r["fotocasa_id"]
    )

for codigo, ids in ids_por_municipio.items():

    if len(ids) != 1:
        raise ValueError(
            f"El municipio {codigo} tiene varios IDs Fotocasa: {ids}"
        )

# Comprobar que no se repiten IDs entre municipios.
ids_unicos = {
    next(iter(ids))
    for ids in ids_por_municipio.values()
}

if len(ids_unicos) != MUNICIPIOS_ESPERADOS:
    raise ValueError(
        f"Hay IDs Fotocasa compartidos o repetidos: "
        f"{len(ids_unicos)} IDs para {MUNICIPIOS_ESPERADOS} municipios."
    )

# Comprobar nombres coherentes dentro de cada municipio.
nombres_por_municipio = defaultdict(set)

for r in registros:
    nombres_por_municipio[r["municipio_codigo"]].add(
        r["municipio_oficial"]
    )

for codigo, nombres in nombres_por_municipio.items():

    if len(nombres) != 1:
        raise ValueError(
            f"Nombres oficiales inconsistentes en {codigo}: {nombres}"
        )

# Comprobar duplicados.
claves = [
    (r["municipio_codigo"], r["tipo"], r["fecha"])
    for r in registros
]

duplicados = len(claves) - len(set(claves))

if duplicados:
    raise ValueError(
        f"Se han encontrado {duplicados} registros duplicados."
    )

# Agrupar por municipio y tipo.
grupos = defaultdict(list)

for r in registros:
    grupos[(r["municipio_codigo"], r["tipo"])].append(r)

series_esperadas = MUNICIPIOS_ESPERADOS * 2

if len(grupos) != series_esperadas:
    raise ValueError(
        f"Se esperaban {series_esperadas} series "
        f"y hay {len(grupos)}."
    )

# Validar las 82 mensualidades de cada serie.
informe = []

for (codigo, tipo), serie in sorted(grupos.items()):

    serie.sort(key=lambda r: r["fecha"])

    fechas = [r["fecha"] for r in serie]

    correcto = (
        len(serie) == REGISTROS_POR_SERIE
        and fechas == MESES_ESPERADOS
    )

    informe.append({
        "municipio_codigo": codigo,
        "municipio": serie[0]["municipio_oficial"],
        "tipo": tipo,
        "registros": len(serie),
        "fecha_inicio": fechas[0] if fechas else "",
        "fecha_fin": fechas[-1] if fechas else "",
        "estado": "correcto" if correcto else "error"
    })

    if not correcto:
        raise ValueError(
            f"Serie incorrecta: {codigo}, {tipo}. "
            f"Registros: {len(serie)}."
        )

total_esperado = (
    MUNICIPIOS_ESPERADOS
    * 2
    * REGISTROS_POR_SERIE
)

if len(registros) != total_esperado:
    raise ValueError(
        f"Total incorrecto: {len(registros)}. "
        f"Esperado: {total_esperado}."
    )

# Ordenar todos los registros.
registros.sort(
    key=lambda r: (
        r["municipio_codigo"],
        r["tipo"],
        r["fecha"]
    )
)


# ============================================================
# GUARDAR RESULTADOS
# ============================================================

CARPETA_INFORMES.mkdir(parents=True, exist_ok=True)

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

with open(
    ARCHIVO_INFORME,
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    escritor = csv.DictWriter(
        f,
        fieldnames=[
            "municipio_codigo",
            "municipio",
            "tipo",
            "registros",
            "fecha_inicio",
            "fecha_fin",
            "estado"
        ],
        delimiter=";"
    )

    escritor.writeheader()
    escritor.writerows(informe)


# ============================================================
# RESUMEN FINAL
# ============================================================

print("\n" + "=" * 65)
print("RESUMEN DE CONSOLIDACION")
print("=" * 65)

print("Municipios:", len(municipios))
print("IDs Fotocasa unicos:", len(ids_unicos))
print("Series:", len(grupos))
print("Series de alquiler:", sum(1 for _, t in grupos if t == "alquiler"))
print("Series de venta:", sum(1 for _, t in grupos if t == "venta"))
print("Registros totales:", len(registros))
print("Duplicados:", duplicados)
print("Series validadas:", len(informe))

print("\nPeriodo:", MESES_ESPERADOS[0], "-", MESES_ESPERADOS[-1])

print("\nARCHIVOS GENERADOS:")
print(ARCHIVO_SALIDA_CSV)
print(ARCHIVO_SALIDA_JSON)
print(ARCHIVO_INFORME)

print("\nConsolidacion y validacion terminadas correctamente.")
