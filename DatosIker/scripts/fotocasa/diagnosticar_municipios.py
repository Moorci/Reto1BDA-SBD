
from pathlib import Path
from collections import Counter
from openpyxl import load_workbook

archivo = Path("originales/fotocasa/MunicipiosCAE_2025_19_02.xlsx")

def normalizar_codigo(valor, longitud):
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    if not texto.isdigit():
        return ""
    return texto.zfill(longitud)

wb = load_workbook(archivo, data_only=True)
ws = wb["EAE"]

municipios = []

for numero_fila, fila in enumerate(
    ws.iter_rows(min_row=10, values_only=True),
    start=10
):
    provincia = normalizar_codigo(fila[0], 2)
    codigo_municipio = normalizar_codigo(fila[2], 3)
    nombre = str(fila[3]).strip() if fila[3] else ""

    if provincia in ("01", "48", "20") and codigo_municipio:
        codigo_completo = provincia + codigo_municipio

        municipios.append({
            "fila_excel": numero_fila,
            "codigo": codigo_completo,
            "nombre": nombre,
            "provincia": provincia
        })

print("\nMUNICIPIOS ENCONTRADOS:", len(municipios))

print("\nDISTRIBUCIÓN POR PROVINCIA:")
for provincia, cantidad in Counter(
    m["provincia"] for m in municipios
).items():
    print(provincia, cantidad)

print("\nTODOS LOS REGISTROS:")
for m in municipios:
    print(
        f"Fila {m['fila_excel']:3} | "
        f"{m['codigo']} | {m['nombre']}"
    )

print("\nCÓDIGOS DUPLICADOS:")
codigos = [m["codigo"] for m in municipios]
for codigo, cantidad in Counter(codigos).items():
    if cantidad > 1:
        print(codigo, cantidad)
