import os
import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import pandas as pd

os.makedirs("DatosAkira/Vivienda", exist_ok=True)

def crear_csv_ventas(inmuebles):
    ruta = "DatosAkira/Vivienda/datos_quorum_ventas.csv"
    archivo_existe = os.path.isfile(ruta)
    
    with open(ruta, "a", encoding="utf-8-sig", newline="") as fichero:
        cabeceras = ["titulo", "municipio_zona", "precio_venta", "metros_cuadrados", "habitaciones", "banos", "enlace_anuncio", "fuente"]   
        escritor = csv.DictWriter(fichero, fieldnames=cabeceras)
        
        if not archivo_existe:
            escritor.writeheader()
            
        escritor.writerows(inmuebles)

def crear_json_ventas(inmuebles):
    with open("DatosAkira/Vivienda/datos_quorum_ventas.json", "a", encoding="utf-8") as fichero:
        json.dump(inmuebles, fichero, ensure_ascii=False, indent=4)
        fichero.write("\n")

def coger_contenido(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    respuesta = requests.get(url, headers=headers)
    
    if respuesta.status_code == 200:
        return BeautifulSoup(respuesta.text, "html.parser")
    return None

def crear_archivos_ventas(soup):
    inmuebles = []
    articulos = soup.find_all('article', class_='ficha-prop')
    
    for articulo in articulos:
        caja_precio = articulo.find('div', class_='ficha-prop-precio')
        precio_texto = caja_precio.text.strip() if caja_precio else ""
        precio_limpio = precio_texto.replace('€', '').replace('.', '').strip()
        
        caja_enlace = articulo.find('a', class_='linkall')
        enlace = caja_enlace['href'] if caja_enlace else ""
        
        caja_titulo = articulo.find('h3', class_='nombre-prop')
        titulo = caja_titulo.text.strip() if caja_titulo else "Sin título"
        
        metros = habitaciones = banos = None
        
        detalles = articulo.find_all('div', class_='detalle_inmo')
        for detalle in detalles:
            texto = detalle.get_text(strip=True).lower()
            if 'm' in texto:
                parte_numerica = texto.split('m')[0]
                metros = ''.join(filter(str.isdigit, parte_numerica))
            elif 'hab' in texto:
                habitaciones = ''.join(filter(str.isdigit, texto))
            elif 'baño' in texto:
                banos = ''.join(filter(str.isdigit, texto))
                
        if precio_limpio:
            inmueble = {
                "titulo": titulo,
                "municipio_zona": "Revisar en detalle",
                "precio_venta": int(precio_limpio),
                "metros_cuadrados": int(metros) if metros else None,
                "habitaciones": int(habitaciones) if habitaciones else None,
                "banos": int(banos) if banos else None,
                "enlace_anuncio": enlace,
                "fuente": "Inmobiliaria Quorum"
            }
            inmuebles.append(inmueble)
            
    if inmuebles:
        crear_csv_ventas(inmuebles)
        crear_json_ventas(inmuebles)

url_base = "https://inmobiliariaquorum.com/viviendas-venta/"
pagina = "?orden=recientes"

print("Iniciando extracción de VENTA...")

while True:
    siguiente = None
    url_completa = url_base + pagina if not pagina.startswith("http") else pagina
    print("Analizando:", url_completa)
    
    soup = coger_contenido(url_completa)
    
    if soup:
        crear_archivos_ventas(soup)

        botones = soup.find_all("a")
        for boton in botones:
            texto_boton = boton.get_text(strip=True)
            if "Siguiente" in texto_boton:
                siguiente = boton.get("href")
                print("-> Botón Siguiente encontrado. Pasando a la próxima página...")
                break

    if siguiente is None:
        print("Fin de la extracción. No hay más páginas.")
        break

    pagina = siguiente
    time.sleep(2) 

ruta_csv = "DatosAkira/Vivienda/datos_quorum_ventas.csv"
if os.path.exists(ruta_csv):
    df_ventas = pd.read_csv(ruta_csv)
    print(f"\n¡Éxito! Se han extraído {len(df_ventas)} viviendas en venta en total.")
    print("\nVista previa de los primeros 10 pisos extraídos:")
    print(df_ventas.head(10).to_string())
else:
    print("\nNo se encontró el archivo generado. Comprueba posibles errores de red.")