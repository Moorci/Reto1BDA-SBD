
import requests
import json

BASE_URL = "https://www.eustat.eus/bankupx/api/v1/es/DB/"

TABLAS = [
    "PX_173402_crpf_rpf_rp03.px",
    "PX_173402_crpf_rpf_rp30.px"
]

for tabla in TABLAS:

    print("\n" + "=" * 60)
    print("PRUEBA:", tabla)
    print("=" * 60)

    url = BASE_URL + tabla

    try:
        # 1. Consultar metadatos mediante GET
        print("\n--- PETICION GET ---")

        get = requests.get(url, timeout=60)

        print("Estado HTTP:", get.status_code)
        print("Content-Type:", get.headers.get("Content-Type"))

        if get.status_code == 200:
            metadatos = get.json()

            print("Tipo de respuesta:", type(metadatos).__name__)

            if isinstance(metadatos, dict):
                print("Claves:", list(metadatos.keys()))

        else:
            print("Respuesta:", get.text[:500])

        # 2. Consultar datos mediante POST
        print("\n--- PETICION POST ---")

        consulta = {
            "query": [],
            "response": {
                "format": "json-stat"
            }
        }

        post = requests.post(
            url,
            json=consulta,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            },
            timeout=180
        )

        print("Estado HTTP:", post.status_code)
        print("Content-Type:", post.headers.get("Content-Type"))
        print("Respuesta (primeros 1500 caracteres):")
        print(post.text[:1500])

        try:
            datos = post.json()

            print("\nTipo JSON:", type(datos).__name__)

            if isinstance(datos, dict):
                print("Claves:", list(datos.keys()))
                print("Valor de class:", datos.get("class"))

        except ValueError:
            print("\nLa respuesta no es JSON válido.")

    except Exception as error:
        print("ERROR:", error)

print("\nPruebas finalizadas.")
