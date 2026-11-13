# Guion de demostración

## Preparación previa

1. Abrir PowerShell en la carpeta raíz del proyecto.
2. Confirmar que Python 3.12 y las dependencias del archivo
   `requirements.txt` están instalados. No se necesita incluir `.conda`.
3. Comprobar MongoDB. HDFS y Kafka solo se ejecutan si los servicios del
   entorno están disponibles; no se presupone que estén instalados ni
   arrancados en otro ordenador.
4. No repetir scrapers ni descargas durante la exposición. Los datos validados
   están guardados y Fotocasa tiene límites de frecuencia.
5. No mostrar ni copiar URI, contraseñas ni tokens en la terminal o en la
   grabación.

## Demostración principal

### 1. Comprobar MongoDB

```powershell
.\.venv\Scripts\python.exe -B -c "from pymongo import MongoClient; from src.config import MONGO_URI; c=MongoClient(MONGO_URI,serverSelectionTimeoutMS=3000); c.admin.command('ping'); print('MongoDB accesible'); c.close()"
```

### 2. Comprobar la base canónica y los recuentos

```powershell
.\.venv\Scripts\python.exe -B -c "from pymongo import MongoClient; from src.config import MONGO_URI,PHASE3_DATABASE_NAME; c=MongoClient(MONGO_URI,serverSelectionTimeoutMS=3000); d=c[PHASE3_DATABASE_NAME]; print({n:d[n].count_documents({}) for n in ('municipios','precios_fotocasa','anuncios_pisoscom','alquiler_emal','renta_personal_eustat','demanda_vpo','anuncios_stream_fase5')}); c.close()"
```

### 3. Validar y repetir la carga idempotente

```powershell
.\.venv\Scripts\python.exe -B .\src\cargar_mongodb_fase3.py --dry-run
.\.venv\Scripts\python.exe -B .\src\cargar_mongodb_fase3.py
```

El dry-run valida las 11 fuentes sin conexión ni escritura. La carga no borra
colecciones; en una base ya actualizada, la segunda ejecución debe informar
cero inserciones y modificaciones.

### 4. Demostrar CRUD y atomicidad

```powershell
.\.venv\Scripts\python.exe -B .\src\crud_demostracion_fase3.py
```

La salida debe confirmar Insert, Find, Update y Delete, 200 incrementos
atómicos concurrentes con total exacto y la eliminación del documento
temporal.

### 5–7. Consultas, pipelines e índices

```powershell
.\.venv\Scripts\python.exe -B .\src\consultas_fase4.py
```

El comando ejecuta las cinco consultas, los tres Aggregation Pipelines y
`explain()` con y sin índice. La comparación observada produjo `COLLSCAN`
(41.164 documentos) e `IXSCAN` (10 documentos y 10 claves), con los mismos
10 resultados. Los resultados se guardan en
`resultados\fase4\consultas_y_agregaciones.json`.

### 8. Comprobar HDFS y recuperar una muestra

Configurar `HDFS_URL`, `HDFS_USER` y `HDFS_ROOT` para el clúster accesible
desde este equipo. El verificador usa WebHDFS y es de solo lectura:

```powershell
.\.venv\Scripts\python.exe -B -m src.HDFS.verificar_hdfs
```

La carga verificada contiene 269 originales y 21 procesados; los 21
procesados coinciden por SHA-256 con los archivos locales. No volver a subir
los originales. `subir_procesados.py --dry-run` solo prepara el manifiesto local
y no demuestra por sí solo la lectura desde HDFS. El verificador recupera el
CSV Pisos.com y comprueba las 1.041 filas y cabeceras sin escribir en HDFS.

### 9–11. Replay Kafka y comprobación en MongoDB

Crear o confirmar el tópico:

```powershell
.\.venv\Scripts\python.exe -B .\src\fase5_streaming.py crear-topic
```

En una primera terminal, iniciar el consumidor y esperar el mensaje de
disponibilidad:

```powershell
.\.venv\Scripts\python.exe -u -B .\src\fase5_streaming.py consumidor
```

En una segunda terminal, iniciar el productor:

```powershell
.\.venv\Scripts\python.exe -u -B .\src\fase5_streaming.py productor
```

El consumidor se inicia primero para estar listo antes de la publicación. El
productor reproduce los 1.041 anuncios del CSV histórico de Pisos.com desde
HDFS; no obtiene anuncios nuevos. Comprobar el resultado sin imprimir datos
del anuncio:

```powershell
.\.venv\Scripts\python.exe -B -c "from pymongo import MongoClient; from src.config import MONGO_URI,PHASE3_DATABASE_NAME; c=MongoClient(MONGO_URI,serverSelectionTimeoutMS=3000); x=c[PHASE3_DATABASE_NAME]['anuncios_stream_fase5']; print('eventos:',x.count_documents({'tipo_evento':'reproduccion_historica'}),'con codigo municipal:',x.count_documents({'municipio_codigo':{'$exists':True}})); c.close()"
```

La colección `anuncios_stream_fase5` es independiente de `anuncios_pisoscom`.
El CSV fuente no contiene códigos municipales, por lo que el replay no los
inventa ni los asigna.

### 12–14. Análisis, informe y pruebas

```powershell
.\.venv\Scripts\python.exe -B .\src\cargar_salarios_regionales.py --dry-run
.\.venv\Scripts\python.exe -B .\src\cargar_salarios_regionales.py
.\.venv\Scripts\python.exe -B .\src\analisis_fase6.py
Start-Process .\resultados\fase6\informe_fase6.html
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

El cargador salarial solo escribe en la base auxiliar configurada por
`MONGO_DB`; no modifica las colecciones canónicas. El informe compara las tres
capitales, muestra tamaños muestrales y genera CSV, JSON y siete SVG.

## Mensajes para la defensa

- Fotocasa es precio de oferta, EMAL alquiler registrado y Pisos.com anuncios
  individuales: no representan la misma población ni el mismo mercado.
- El escenario de alquiler de 60 m² compara precio municipal con remuneración
  neta juvenil **regional** 16–29; no es esfuerzo individual ni ingreso
  observado en cada municipio.
- Eustat RP03 tiene grupos de edad, pero solo geografía Euskadi; RP11S tiene
  municipios, pero no edad. No se combinan. No hay ingresos juveniles
  municipales verificados y no se calcula un esfuerzo juvenil municipal.
- La renta municipal Eustat del trabajo es una magnitud personal anual de todos
  los grupos de edad; no es salario neto juvenil.
- Etxebide es una fotografía; las supresiones no se convierten en cero.
- Varias trayectorias Fotocasa se repiten entre municipios. El ranking de Fase
  6 utiliza series no compartidas y no cuenta copias como observaciones
  independientes.
