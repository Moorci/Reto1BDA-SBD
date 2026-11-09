#!/usr/bin/env python3
"""
Convierte el libro XLSM de demanda de vivienda de Etxebide a un CSV limpio.

Uso:
    python convertir_etxebide.py "Demandantes-Etxebide-Municipio-2026-07-01.xlsm"

Salida:
    Demandantes-Etxebide-Municipio-2026-07-01_limpio.csv

La hoja Datos_Base contiene los datos de todos los municipios en formato largo.
La hoja Datos es una tabla/pivot de presentación y no se usa como fuente principal.
Las celdas "s.e." se convierten en valor numérico vacío y se conserva su significado
en una columna de estado para cada métrica.
"""

from pathlib import Path
import argparse
import re
import sys

import pandas as pd


COLUMNAS_ESPERADAS = [
    "MUNICIPIO",
    "Grupo",
    "Literal",
    "Empadronado_Compra",
    "Empadronado_Alquiler",
    "Empadronados",
    "NoEmpadronado_Compra",
    "NoEmpadronado_Alquiler",
    "NoEmpadronados",
    "Total",
]

COLUMNAS_NUMERICAS = [
    "Empadronado_Compra",
    "Empadronado_Alquiler",
    "Empadronados",
    "NoEmpadronado_Compra",
    "NoEmpadronado_Alquiler",
    "NoEmpadronados",
    "Total",
]


def nombre_columna(texto: str) -> str:
    """Normaliza un nombre de municipio sin alterar nombres con barras internas."""
    texto = str(texto).strip()
    # En el archivo el municipio se repite en euskera/castellano separado por " / ".
    partes = texto.split(" / ", maxsplit=1)
    return partes[0].strip()


def limpiar_texto(serie: pd.Series) -> pd.Series:
    return serie.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()


def convertir(entrada: Path, salida: Path) -> None:
    if not entrada.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {entrada}")

    # openpyxl lee las celdas y no ejecuta macros. No se modifica el XLSM original.
    df = pd.read_excel(
        entrada,
        sheet_name="Datos_Base",
        engine="openpyxl",
        dtype=object,
    )

    # Eliminar filas totalmente vacías y normalizar encabezados.
    df = df.dropna(how="all").copy()
    df.columns = [str(c).strip() for c in df.columns]

    faltan = [c for c in COLUMNAS_ESPERADAS if c not in df.columns]
    if faltan:
        raise ValueError(
            "La hoja Datos_Base no tiene las columnas esperadas. "
            f"Faltan: {faltan}. Columnas encontradas: {list(df.columns)}"
        )

    df = df[COLUMNAS_ESPERADAS].copy()

    # Limpiar campos categóricos.
    for col in ["MUNICIPIO", "Grupo", "Literal"]:
        df[col] = limpiar_texto(df[col])

    # Conservar el texto completo original y crear un nombre municipal principal.
    df.insert(1, "Municipio", df["MUNICIPIO"].map(nombre_columna))
    df = df.rename(columns={"MUNICIPIO": "Municipio_bilingue"})

    # Convertir las métricas a números. Para cada "s.e." se deja el número vacío
    # y se crea una columna de estado que distingue dato suprimido de dato numérico.
    for col in COLUMNAS_NUMERICAS:
        original = df[col].astype("string").str.strip()
        suprimido = original.str.lower().eq("s.e.").fillna(False)
        numerico = pd.to_numeric(original.mask(suprimido), errors="coerce")

        # Detectar valores no numéricos inesperados en lugar de ocultarlos.
        inesperados = original.notna() & ~suprimido & numerico.isna()
        if inesperados.any():
            ejemplos = original[inesperados].drop_duplicates().head(5).tolist()
            raise ValueError(
                f"Valores inesperados en {col}: {ejemplos}. "
                "Revisa si el formato del archivo ha cambiado."
            )

        df[col] = numerico
        df[f"{col}_estado"] = "disponible"
        df.loc[suprimido, f"{col}_estado"] = "s.e. (dato no publicado/suprimido)"
        df.loc[original.isna(), f"{col}_estado"] = "vacío en origen"

    # Retirar filas que no tengan municipio o categoría.
    df = df[df["Municipio"].notna() & df["Grupo"].notna() & df["Literal"].notna()]
    df = df.sort_values(["Municipio", "Grupo", "Literal"], kind="stable")

    salida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        salida,
        index=False,
        encoding="utf-8-sig",
        sep=",",
        na_rep="",
        lineterminator="\n",
    )

    print(f"CSV creado: {salida.resolve()}")
    print(f"Filas: {len(df):,}")
    print(f"Municipios: {df['Municipio'].nunique():,}")
    print(f"Grupos: {df['Grupo'].nunique():,}")
    print("Nota: las macros no se ejecutan; se leen únicamente los datos guardados.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convierte el XLSM de demandantes de Etxebide a CSV limpio."
    )
    parser.add_argument("entrada", help="Ruta del archivo XLSM")
    parser.add_argument(
        "-o", "--salida",
        help="Ruta del CSV de salida (por defecto, junto al XLSM con sufijo _limpio.csv)",
    )
    args = parser.parse_args()

    entrada = Path(args.entrada)
    salida = Path(args.salida) if args.salida else entrada.with_name(
        f"{entrada.stem}_limpio.csv"
    )

    try:
        convertir(entrada, salida)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
