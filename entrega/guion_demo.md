# Guion de demostración

## Preparación

1. Abrir PowerShell en `C:\Users\Alvaro.Morcillo\Desktop\Reto1`.
2. Comprobar que MongoDB está accesible mediante la configuración local de
   `MONGO_URI`. No mostrar ni copiar valores de conexión con credenciales.
3. Para el flujo Kafka, conectarse a la red donde estén disponibles HDFS y
   Kafka. La carga de los conjuntos procesados se puede repetir con el
   cargador idempotente; no repetir la subida inicial de originales.
4. No ejecutar de nuevo los scrapers durante la exposición: los conjuntos
   validados ya están guardados y Fotocasa tiene límites de frecuencia.

## Secuencia principal

### 1. Validar fuentes sin escribir en MongoDB

```powershell
.\.conda\python.exe -B .\src\cargar_mongodb_fase3.py --dry-run
```

El resultado esperado indica 11 fuentes canónicas, 306.711 documentos previstos
y 252 códigos municipales. El modo `--dry-run` no abre conexión ni escribe.

### 2. Demostrar CRUD PyMongo

```powershell
.\.conda\python.exe -B .\src\crud_demostracion_fase3.py
```

La salida debe confirmar Insert, Find, Update y Delete. El script usa un ID
aleatorio y elimina el documento temporal también si la demostración falla.

### 3. Ejecutar consultas, pipelines y explain

```powershell
.\.conda\python.exe -B .\src\consultas_fase4.py
```

Se generan cinco resultados de consulta, tres agregaciones y la comparación
`COLLSCAN`/`IXSCAN` en `resultados/fase4/consultas_y_agregaciones.json`.

### 4. Generar los resultados visuales

```powershell
.\.conda\python.exe -B .\src\cargar_salarios_regionales.py --dry-run
.\.conda\python.exe -B .\src\cargar_salarios_regionales.py
.\.conda\python.exe -B .\src\analisis_fase6.py
Start-Process .\resultados\fase6\informe_fase6.html
```

El cargador importa únicamente `remuMedia.csv` e `iovj-empleo-economico.csv`
mediante upsert a la base indicada por `MONGO_DB` (por defecto
`reto_vivienda`). No vuelve a extraer datos ni modifica la base canónica de
vivienda.

Mostrar el informe HTML y los siete SVG de `resultados/fase6/graficos`. Señalar
las fechas, el tamaño muestral de Pisos.com, el escenario regional y el cruce
municipal EMAL-Eustat de 2024. Aclarar que «Renta del trabajo» no está
desglosada por edad ni equivale a salario neto, y que ninguno de los cocientes
mide esfuerzo individual. También indicar que varias series Fotocasa están
repetidas entre municipios.

### 5. Ejecutar las pruebas

```powershell
.\.conda\python.exe -B -m unittest discover -s tests -v
```

## Demostración opcional del replay Kafka

Este paso requiere HDFS y Kafka disponibles y reproduce el snapshot histórico de
Pisos.com; no descarga anuncios nuevos.

Para verificar la zona procesada en HDFS:

```powershell
.\.conda\python.exe -B .\src\HDFS\subir_procesados.py --dry-run
.\.conda\python.exe -B .\src\HDFS\subir_procesados.py
```

El script sube `DatosIker\procesados` bajo `\user\<usuario>\reto1\procesados`,
preserva las subcarpetas y verifica cada archivo con SHA-256. La carga de
originales usa un notebook distinto y ya está completada.

Primero, comprobar o crear el tópico:

```powershell
.\.conda\python.exe -B .\src\fase5_streaming.py crear-topic
```

En la primera terminal, iniciar el consumidor:

```powershell
.\.conda\python.exe -u -B .\src\fase5_streaming.py consumidor
```

Esperar el mensaje que indica que el consumidor está listo. En una segunda
terminal, ejecutar:

```powershell
.\.conda\python.exe -u -B .\src\fase5_streaming.py productor
```

El lote esperado contiene 1.041 anuncios y se inserta en
`reto_vivienda_fase3.anuncios_stream_fase5`. En una repetición, los IDs
deterministas evitan duplicar documentos; la salida puede indicar que ya
existían. La colección canónica `anuncios_pisoscom` permanece separada.

No ejecutar `src/HDFS/productor.py` como parte de esta demostración: la carga
inicial de originales ya está completada y no es necesaria para el replay.

## Mensajes clave para explicar

- Los documentos de hechos se relacionan por `municipio_codigo`; las fuentes
  conservan colecciones separadas porque sus unidades y significados difieren.
- La serie Fotocasa es oferta histórica; EMAL mide alquiler registrado;
  Pisos.com son anuncios individuales; Etxebide representa demanda VPO.
- Vitoria-Gasteiz presenta menor alquiler de oferta Fotocasa que las otras dos
  capitales en octubre de 2026; Pisos.com tiene solo un anuncio de alquiler
  válido para Vitoria en la comparación.
- El escenario de 2024 usa remuneración neta regional de 16-29 años: Vitoria
  requiere alrededor del 46 % de la referencia femenina para un alquiler de
  60 m²; Bilbao, 60 %; Donostia, 72 %. Es orientativo, no municipal ni
  individual.
- La renta personal Eustat no es salario. `salAnual.json` es nacional y no se
  aplica como ingreso vasco.
