import requests

URL = "https://www.eustat.eus/bankupx/api/v1/es/DB/PX_173402_crpf_rpf_rp30.px"

consulta = {
    "query": [
        {
            "code": "ámbitos territoriales",
            "selection": {
                "filter": "item",
                "values": ["00001"]
            }
        },
        {
            "code": "percentil (renta personal)",
            "selection": {
                "filter": "item",
                "values": ["20"]
            }
        },
        {
            "code": "sexo",
            "selection": {
                "filter": "item",
                "values": ["10"]
            }
        },
        {
            "code": "periodo",
            "selection": {
                "filter": "item",
                "values": ["2024"]
            }
        }
    ],
    "response": {
        "format": "json-stat"
    }
}

try:
    respuesta = requests.post(
        URL,
        json=consulta,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        timeout=180
    )

    print("Estado HTTP:", respuesta.status_code)
    print("Content-Type:", respuesta.headers.get("Content-Type"))

    respuesta.raise_for_status()

    datos = respuesta.json()

    if "dataset" in datos:
        dataset = datos["dataset"]

        print("\nCONSULTA CORRECTA")
        print("Dimensiones:", len(dataset["dimension"]))
        print("Valores:", dataset["value"])

    else:
        print("Respuesta inesperada:")
        print(respuesta.text[:1000])

except Exception as error:
    print("\nERROR:", error)

print("\nPrueba finalizada.")