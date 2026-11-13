
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]

ARCHIVO = (
    RAIZ / "informes" / "pisoscom"
    / "validacion_geografica_pisoscom.csv"
)

PENDIENTES = (
    RAIZ / "informes" / "pisoscom"
    / "municipios_sin_correspondencia.csv"
)

df = pd.read_csv(
    ARCHIVO,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

pendientes = pd.read_csv(
    PENDIENTES,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

print("=" * 65)
print("REVISIÓN DE CORRESPONDENCIAS GEOGRÁFICAS")
print("=" * 65)

# ------------------------------------------------------------
# 1. Revisar coincidencias normalizadas
# ------------------------------------------------------------

normalizadas = df[
    df["estado_correspondencia"] == "coincidencia_normalizada"
]

print("\n1. COINCIDENCIAS NORMALIZADAS")
print("-" * 65)

resumen = (
    normalizadas.groupby(
        [
            "provincia_pisos",
            "municipio_extraido",
            "municipio_oficial_fotocasa",
            "municipio_codigo"
        ],
        dropna=False
    )
    .size()
    .reset_index(name="numero_anuncios")
    .sort_values(
        ["provincia_pisos", "municipio_extraido"]
    )
)

print(resumen.to_string(index=False))

print(
    f"\nAnuncios normalizados: {len(normalizadas)}"
)

print(
    f"Municipios/variantes diferentes: {len(resumen)}"
)

# ------------------------------------------------------------
# 2. Revisar municipios excluidos
# ------------------------------------------------------------

excluidos = df[
    df["estado_correspondencia"]
    == "municipio_excluido_catalogo"
]

print("\n2. MUNICIPIOS EXCLUIDOS")
print("-" * 65)

if excluidos.empty:
    print("No hay municipios excluidos.")

else:
    print(
        excluidos[
            [
                "provincia_pisos",
                "localidad_zona_original",
                "municipio_extraido",
                "municipio_oficial_fotocasa",
                "estado_catalogo",
                "municipio_codigo"
            ]
        ].to_string(index=False)
    )

# ------------------------------------------------------------
# 3. Revisar CSV de pendientes
# ------------------------------------------------------------

print("\n3. ARCHIVO DE PENDIENTES")
print("-" * 65)

print(f"Registros pendientes: {len(pendientes)}")

if not pendientes.empty:
    print(pendientes.to_string(index=False))

# ------------------------------------------------------------
# 4. Comprobar códigos vacíos y duplicados
# ------------------------------------------------------------

asignados = df[
    df["estado_correspondencia"].isin([
        "coincidencia_exacta",
        "coincidencia_normalizada"
    ])
]

codigos_vacios = asignados[
    asignados["municipio_codigo"].str.strip() == ""
]

print("\n4. COMPROBACIONES DE CÓDIGOS")
print("-" * 65)

print(
    "Correspondencias sin código: ",
    len(codigos_vacios)
)

print(
    "Anuncios con código asignado: ",
    len(asignados)
)

print(
    "Códigos municipales diferentes: ",
    asignados["municipio_codigo"].nunique()
)

print("\nRevisión finalizada.")
