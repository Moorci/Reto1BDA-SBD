
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import posixpath
import re

ARCHIVO = Path(
    "originales/EMAL.-Barrios-Municipios.-2016-2026_es.xlsx"
)

NS = {
    "main": "http://schemas.openxmlformats.org/"
            "spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/"
           "officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/"
           "package/2006/relationships",
}


def nombre_columna(referencia):
    """Convierte A1, B3, AA10... en su número de columna."""
    letras = re.match(r"[A-Z]+", referencia).group()
    numero = 0

    for letra in letras:
        numero = numero * 26 + ord(letra) - ord("A") + 1

    return numero


if not ARCHIVO.exists():
    raise FileNotFoundError(
        f"No se encuentra el archivo: {ARCHIVO.resolve()}"
    )

with ZipFile(ARCHIVO) as excel:
    # Leer las cadenas compartidas del Excel
    cadenas = []

    if "xl/sharedStrings.xml" in excel.namelist():
        raiz = ET.fromstring(excel.read("xl/sharedStrings.xml"))

        for elemento in raiz.findall("main:si", NS):
            cadenas.append(
                "".join(
                    t.text or ""
                    for t in elemento.findall(".//main:t", NS)
                )
            )

    # Leer las relaciones entre las hojas y sus archivos XML
    relaciones = ET.fromstring(
        excel.read("xl/_rels/workbook.xml.rels")
    )

    mapa_relaciones = {
        r.attrib["Id"]: r.attrib["Target"]
        for r in relaciones.findall("pkg:Relationship", NS)
    }

    libro = ET.fromstring(excel.read("xl/workbook.xml"))

    hojas = libro.findall("main:sheets/main:sheet", NS)

    print(f"Archivo: {ARCHIVO.name}")
    print(f"Número de hojas: {len(hojas)}")

    for hoja in hojas:
        nombre = hoja.attrib["name"]
        id_relacion = hoja.attrib[
            "{http://schemas.openxmlformats.org/"
            "officeDocument/2006/relationships}id"
        ]

        destino = mapa_relaciones[id_relacion]

        if destino.startswith("/"):
            ruta_xml = destino.lstrip("/")
        else:
            ruta_xml = posixpath.normpath(
                posixpath.join("xl", destino)
            )

        raiz = ET.fromstring(excel.read(ruta_xml))

        print("\n" + "=" * 70)
        print(f"HOJA: {nombre}")
        print("=" * 70)

        filas = raiz.findall(".//main:sheetData/main:row", NS)

        print(f"Filas con contenido: {len(filas)}")
        print("Primeras 12 filas:")

        for fila in filas[:12]:
            valores = []

            for celda in fila.findall("main:c", NS):
                referencia = celda.attrib["r"]
                tipo = celda.attrib.get("t", "")
                valor_xml = celda.find("main:v", NS)

                if tipo == "inlineStr":
                    valor = "".join(
                        t.text or ""
                        for t in celda.findall(".//main:t", NS)
                    )
                elif valor_xml is None:
                    valor = ""
                else:
                    valor = valor_xml.text or ""

                    if tipo == "s":
                        valor = cadenas[int(valor)]

                if str(valor).strip():
                    valores.append(
                        (nombre_columna(referencia), str(valor))
                    )

            valores.sort(key=lambda elemento: elemento[0])

            if valores:
                print(
                    f"Fila {fila.attrib.get('r')}: "
                    + " | ".join(
                        f"{valor}" for _, valor in valores
                    )
                )

print("\nInspección completada.")
