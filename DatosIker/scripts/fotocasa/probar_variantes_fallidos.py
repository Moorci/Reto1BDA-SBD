import requests
import time

variantes = {
    "01017": ["campezo", "kanpezu"],
    "20065": ["soraluze", "placencia-de-las-armas"],
}

base_url = (
    "https://www.fotocasa.es/es/indice-precio-vivienda/"
    "alquiler/{}/todas-las-zonas"
)

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

resultados = []

for codigo, slugs in variantes.items():
    for slug in slugs:
        url = base_url.format(slug)

        try:
            respuesta = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            print(
                f"{codigo} | {slug} | "
                f"HTTP {respuesta.status_code}"
            )

            resultados.append({
                "codigo": codigo,
                "slug": slug,
                "url": url,
                "http_status": respuesta.status_code
            })

        except requests.RequestException as error:
            print(f"{codigo} | {slug} | ERROR: {error}")

        time.sleep(5)

print("\nPrueba terminada.")