import os
import pandas as pd
import numpy as np

# 1. Creamos un DataFrame simulando datos para el reto de vivienda en Euskadi
np.random.seed(42)
municipios = ["Bilbao", "Vitoria-Gasteiz", "Donostia/San Sebastián", "Barakaldo", "Getxo", "Irun", "Portugalete", "Santurtzi", "Basauri", "Durango"]

data = {
    "municipio": np.random.choice(municipios, 50),
    "territorio": np.random.choice(["Bizkaia", "Araba/Álava", "Gipuzkoa"], 50),
    "anio": np.random.choice([2021, 2022, 2023, 2024, 2025], 50),
    "salario_medio_anual_joven": np.random.randint(15000, 26000, 50),
    "precio_medio_alquiler_mes": np.random.randint(600, 1400, 50),
    "precio_medio_compra_m2": np.random.randint(2000, 5500, 50),
    "superficie_media_vivienda": np.random.randint(60, 110, 50)
}

df = pd.DataFrame(data)

# 2. Calculamos la tasa de esfuerzo analítica para el reto (gasto anual en alquiler respecto al salario)
df["gasto_anual_alquiler"] = df["precio_medio_alquiler_mes"] * 12
df["tasa_esfuerzo_alquiler_pct"] = round((df["gasto_anual_alquiler"] / df["salario_medio_anual_joven"]) * 100, 2)

# 3. Guardamos el archivo CSV directamente en tu carpeta para evitar bloqueos de permisos
carpeta = "DatosAkira"
os.makedirs(carpeta, exist_ok=True) # Crea la carpeta si no existe

# Generamos la ruta completa (DatosAkira/datos_reto_vivienda_euskadi.csv)
ruta_destino = os.path.join(carpeta, "datos_reto_vivienda_euskadi.csv")

df.to_csv(ruta_destino, index=False, encoding="utf-8-sig")

print(f"¡Éxito! Archivo generado con {len(df)} registros en: {ruta_destino}")
print("\nVista previa de los datos:")
print(df.head(3))

import os

ruta = os.path.join("DatosAkira", "datos_reto_vivienda_euskadi.csv")

if os.path.exists(ruta):
    print("¡El archivo existe!")
    print(f"Ruta completa: {os.path.abspath(ruta)}")
    print(f"Tamaño: {os.path.getsize(ruta)} bytes")
else:
    print("El archivo NO existe en esa ruta.")
    print(f"Buscado en: {os.path.abspath(ruta)}")
    print(f"Carpeta de trabajo actual: {os.getcwd()}")