import requests

SERVIDORES = [
    "https://www.eustat.eus",
    "https://eu-mig.eustat.eus",
    "https://es-mig.eustat.eus"
]

TABLA = "PX_173402_crpf_rpf_rp30.px"

consulta = {
    "query": [],
    "response": {
        "format": "json-stat"
    }
}

for servidor in SERVIDORES:

    url = f"{servidor}/bankupx/api/v1/es/DB/{TABLA}"

    print("\n" + "=" * 60)
    print("SERVIDOR:", servidor)
    print("=" * 60)

    try:
        respuesta = requests.post(
            url,
            json=consulta,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{servidor}/bankupx/pxweb/es/DB/-/{TABLA}"
            },
            timeout=180
        )

        print("Estado HTTP:", respuesta.status_code)
        print("Content-Type:", respuesta.headers.get("Content-Type"))

        if respuesta.status_code == 200:
            datos = respuesta.json()

            if "dataset" in datos:
                dataset = datos["dataset"]

                print("DESCARGA DE PRUEBA CORRECTA")
                print("Dimensiones:", len(dataset.get("dimension", {})))
                print("Valores:", len(dataset.get("value", [])))
            else:
                print("Respuesta sin clave dataset:")
                print(respuesta.text[:500])
        else:
            print("Respuesta:")
            print(respuesta.text[:500])

    except Exception as error:
        print("ERROR:", error)

print("\nPruebas finalizadas.")