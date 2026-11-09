
import csv
import shutil
from pathlib import Path

CARPETA = Path("originales/fotocasa")

CATALOGO = CARPETA / "catalogo_municipios_fotocasa.csv"

INFORME = Path(
    "informes/fotocasa/prueba_localizacion_municipios.csv"
)

BACKUP = CARPETA / "catalogo_municipios_fotocasa_backup.csv"

CODIGOS_ESPERADOS = {
    "48001",
    "20001",
    "48002",
    "20002",
    "01051",
}

# Leer catálogo original
with open(CATALOGO, encoding="utf-8-sig", newline="") as f:
    lector = csv.DictReader(f, delimiter=";")
    campos = lector.fieldnames
    catalogo = list(lector)

# Leer resultados de la prueba
with open(INFORME, encoding="utf-8-sig", newline="") as f:
    pruebas = list(csv.DictReader(f, delimiter=";"))

# Comprobar que están los cinco municipios esperados
codigos_prueba = {
    fila["municipio_codigo"] for fila in pruebas
}

if codigos_prueba != CODIGOS_ESPERADOS:
    raise ValueError(
        f"Los códigos del informe no coinciden: {codigos_prueba}"
    )

# No modificar nada si alguna prueba no ha sido validada
for fila in pruebas:
    if fila["estado"] != "candidato_valido":
        raise ValueError(
            f"Municipio no validado: {fila['municipio_oficial']} "
            f"({fila['estado']})"
        )

# Crear copia de seguridad
shutil.copy2(CATALOGO, BACKUP)

# Actualizar los registros
actualizados = 0

for prueba in pruebas:

    registro = next(
        (
            fila for fila in catalogo
            if fila["municipio_codigo"] == prueba["municipio_codigo"]
        ),
        None
    )

    if registro is None:
        raise ValueError(
            f"Municipio no encontrado: {prueba['municipio_codigo']}"
        )

    registro["fotocasa_id"] = prueba["fotocasa_id"]
    registro["fotocasa_slug"] = prueba["slug_probado"]
    registro["nombre_fotocasa"] = prueba["nombre_fotocasa"]
    registro["url"] = prueba["url"]
    registro["estado"] = "validado"
    registro["registros_alquiler"] = prueba["registros_alquiler"]
    registro["registros_venta"] = prueba["registros_venta"]

    actualizados += 1

# Guardar catálogo actualizado
with open(
    CATALOGO,
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    escritor = csv.DictWriter(
        f,
        fieldnames=campos,
        delimiter=";"
    )

    escritor.writeheader()
    escritor.writerows(catalogo)

# Resumen
validados = sum(
    fila["estado"] == "validado"
    for fila in catalogo
)

pendientes = sum(
    fila["estado"] == "pendiente"
    for fila in catalogo
)

print("=" * 60)
print("CATALOGO FOTOCASA ACTUALIZADO")
print("=" * 60)

print("Municipios totales:", len(catalogo))
print("Municipios incorporados:", actualizados)
print("Municipios validados:", validados)
print("Municipios pendientes:", pendientes)

print("\nCopia de seguridad:")
print(BACKUP)

print("\nCatálogo actualizado:")
print(CATALOGO)
