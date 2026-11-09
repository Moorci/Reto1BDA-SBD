
from openpyxl import load_workbook
from pathlib import Path

archivo = Path("originales/fotocasa/MunicipiosCAE_2025_19_02.xlsx")

if not archivo.exists():
    raise FileNotFoundError(f"No se encuentra: {archivo}")

libro = load_workbook(archivo, read_only=True, data_only=True)

print("=" * 65)
print("INSPECCION DEL CATALOGO OFICIAL DE MUNICIPIOS")
print("=" * 65)

print("\nHOJAS DEL EXCEL:")
for nombre in libro.sheetnames:
    print("-", nombre)

for hoja in libro.worksheets:
    print("\n" + "=" * 65)
    print("HOJA:", hoja.title)
    print("Filas:", hoja.max_row)
    print("Columnas:", hoja.max_column)

    print("\nPRIMERAS 15 FILAS:")

    for fila in hoja.iter_rows(min_row=1, max_row=min(15, hoja.max_row),
                               values_only=True):
        valores = [
            str(valor) if valor is not None else ""
            for valor in fila
        ]
        print(" | ".join(valores))

libro.close()
