# Matriz de cumplimiento de la rúbrica

La rúbrica oficial incluida en [RETO 1Evaluacion SBD-BDA.pdf](<../RETO 1Evaluacion SBD-BDA.pdf>)
contiene BDA RA1, SBD RA3 y RA4. No incluye un bloque SBD RA1 ni criterios
separados para índices o consistencia. Esos aspectos se documentan al final
como comprobaciones complementarias solicitadas, sin presentarlos como puntos
oficiales.

Las puntuaciones son una estimación razonada del equipo, no una calificación
del profesorado. Se aplica el descriptor más alto cuya evidencia se ha podido
comprobar; las brechas se conservan expresamente.

## BDA — RA1. Gestión de soluciones y almacenamiento

| Criterio del PDF | 0 puntos | 3 puntos | 7 puntos | 10 puntos | Estimación | Evidencia y brecha |
|---|---|---|---|---:|---:|---|
| Extracción de datos mediante Python | No obtiene datos | Obtiene datos de una fuente manualmente | Automatiza una API o scraping | Automatiza API y scraping | **7/10** | Hay scraping automatizado de [Pisos.com](../DatosAlvaro/Vivienda/scraper_pisos.py) y Fotocasa ([localizar_municipios_masivo.py](../DatosIker/scripts/fotocasa/localizar_municipios_masivo.py), [extraer_series_masivo.py](../DatosIker/scripts/fotocasa/extraer_series_masivo.py)). Además, [descargar_datos_eustat.py](../DatosIker/descargar_datos_eustat.py) y [extraer_eustat.py](../DatosIker/extraer_eustat.py) automatizan consultas a la API estadística oficial de Eustat. No hay API inmobiliaria de precios implementada; se estima conservadoramente 7 porque la API existente no proporciona precios de vivienda. |
| Almacenamiento HDFS | No almacena datos | Crea directorios | Guarda y recupera archivos | Organiza originales y procesados y demuestra su recuperación | **10/10** | Verificados 269 originales (136.091.377 bytes) y 21 procesados (205.376.874 bytes) en zonas separadas. Los 21 procesados coinciden por SHA-256; también se recuperó y leyó desde HDFS el CSV histórico de Pisos.com. |
| Kafka | No funciona | Crea un tópico | Envía mensajes con productor Python | Productor y consumidor Python funcionan y procesan mensajes | **10/10** | [fase5_streaming.py](../src/fase5_streaming.py) implementa productor y consumidor JSON. Se verificaron el tópico `reto1_anuncios_iabd-user11`, 1.041 eventos y su persistencia en MongoDB. |
| Integración | No hay integración | Los componentes funcionan por separado | Integra dos o más componentes | Demuestra el flujo completo hasta MongoDB | **10/10** | Se comprobó el replay HDFS → productor Python → Kafka → consumidor Python → `reto_vivienda_fase3.anuncios_stream_fase5`. Es una reproducción histórica, no captación en tiempo real; la colección queda separada de los anuncios canónicos. |

## SBD — RA3. Gestión, almacenamiento y consultas en MongoDB

| Criterio del PDF | 0 puntos | 3 puntos | 7 puntos | 10 puntos | Estimación | Evidencia y brecha |
|---|---|---|---|---:|---:|---|
| Modelado MongoDB | No crea la BD | Crea una colección sin estructura definida | Diseña colecciones con campos adecuados | Justifica el modelo y las relaciones entre datos | **10/10** | Seis colecciones canónicas con tipos y claves definidos; referencias mediante `municipio_codigo` y metadatos pequeños embebidos en el catálogo. Modelo y decisión documentados en [diseño de Fase 3](../DatosIker/informes/diseno_carga_mongodb_fase3.txt). |
| Operaciones PyMongo | No realiza operaciones | Inserta documentos | Inserta, actualiza y elimina documentos | Además, automatiza las operaciones y comprueba resultados | **10/10** | [cargar_mongodb_fase3.py](../src/cargar_mongodb_fase3.py) automatiza la carga idempotente; [crud_demostracion_fase3.py](../src/crud_demostracion_fase3.py) verifica Insert, Find, Update y Delete sobre un documento temporal y confirma su eliminación. Dos cargas reales consecutivas dieron cero inserciones y modificaciones. |
| Consultas | No realiza consultas | Realiza consultas simples | Utiliza filtros, proyecciones y ordenaciones | Combina condiciones y consultas sobre campos anidados o arrays | **10/10** | [consultas_fase4.py](../src/consultas_fase4.py) ejecuta cinco consultas; incluye condiciones compuestas, límites, proyecciones, ordenaciones y filtros sobre `valores.total` y `estados.total`. |
| Aggregation Pipeline | No utiliza agregaciones | Utiliza `$match` y `$group` | Utiliza al menos cuatro etapas diferentes | Combina varias etapas para obtener indicadores complejos | **10/10** | Tres pipelines ejecutados; en conjunto usan `$match`, `$group`, `$lookup`, `$unwind`, `$project`, `$sort` y `$limit`. Resultados y consulta reproducible en [consultas y agregaciones](../resultados/fase4/consultas_y_agregaciones.json). |

## SBD — RA4. Visualización y presentación de resultados

| Criterio del PDF | 0 puntos | 3 puntos | 7 puntos | 10 puntos | Estimación | Evidencia y brecha |
|---|---|---|---|---:|---:|---|
| Gráficos | No crea gráficos | Presenta un gráfico | Presenta tres tipos de gráficos | Presenta tres tipos adecuados a los datos | **10/10** | [Fase 6](../src/analisis_fase6.py) genera siete SVG: series temporales, barras y dispersión, seleccionados para los datos representados. |
| Datos utilizados | No utiliza datos reales | Introduce valores manualmente | Obtiene los datos de MongoDB | Genera gráficos directamente a partir de consultas PyMongo | **10/10** | El análisis consulta las colecciones MongoDB y prepara las tablas y series que alimentan los CSV, JSON y SVG. No se introducen manualmente los valores de los gráficos. |
| Presentación | No presenta resultados | Presenta gráficos sin títulos | Incluye títulos, unidades y leyendas cuando proceda | Además, los gráficos facilitan la comparación entre municipios | **10/10** | Los gráficos incluyen títulos, unidades y etiquetas/leyendas cuando proceden; el [informe HTML](../resultados/fase6/informe_fase6.html) compara las tres capitales y explicita periodos y tamaños muestrales. |
| Interpretación | No interpreta | Describe lo que aparece | Explica tres resultados relevantes | Relaciona resultados y explica sus implicaciones | **7/10** | El [informe final](./informe_final.md) vincula precios, alquileres registrados e ingresos, compara tres capitales y explica límites e implicaciones. No se afirma una tasa juvenil municipal: Eustat no ofrece edad y municipio simultáneamente, por lo que la conclusión económica juvenil solo puede apoyarse en la referencia regional. |

## Comprobaciones complementarias solicitadas

Estos puntos no son criterios ni puntuaciones de la rúbrica oficial.

| Aspecto complementario | Estado estimado | Evidencia y límite |
|---|---:|---|
| SBD RA1 — Integración de fuentes | **10/10** | Se relacionan varias fuentes heterogéneas mediante códigos municipales de cinco caracteres; los cruces se ejecutan con consultas y `$lookup`. Un anuncio Pisos.com sin código permanece sin municipio asignado. |
| SBD RA1 — Construcción del conjunto de datos | **10/10** | Colecciones separadas por fuente, claves referenciales y embedding limitado al catálogo; ver el [modelo](../DatosIker/informes/diseno_carga_mongodb_fase3.txt). |
| SBD RA1 — Limpieza y transformación con PyMongo | **7/10** | La preparación automatizada convierte y valida números, fechas y códigos; conserva nulos/estados y detecta claves naturales duplicadas antes de escribir; los upserts evitan duplicados al reejecutar. Las claves duplicadas de una misma fuente hacen fallar el preflight en vez de corregirse o eliminarse automáticamente. |
| SBD RA1 — Automatización | **7/10** | Preflight, transformación, carga, validación y análisis son ejecutables por scripts sin edición manual de documentos MongoDB. La descarga y preparación de ciertas fuentes y la disponibilidad de servicios HDFS/Kafka requieren pasos separados. |
| RA3 — Índices y rendimiento | **10/10** | `explain()` comparó `COLLSCAN` (41.164 documentos, 0 claves) con `IXSCAN` (10 documentos, 10 claves), devolviendo los mismos 10 resultados; la mejora es reducir documentos examinados. La ejecución queda en el [JSON de Fase 4](../resultados/fase4/consultas_y_agregaciones.json). |
| RA3 — Consistencia | **10/10** | Una operación atómica `$inc` se ejecutó concurrentemente 200 veces sobre un documento y produjo exactamente 200; la prueba de integración y el script CRUD eliminan sus documentos temporales. Las cargas son upserts atómicos por documento; no hay una invariante que requiera actualizar varios documentos indivisiblemente. |
| RA4 — Datos heterogéneos | **10/10** | Fase 6 cruza oferta Fotocasa, EMAL, anuncios, Eustat y Etxebide conservando significado, unidad y periodo por fuente. |
| RA4 — Automatización del análisis | **10/10** | [analisis_fase6.py](../src/analisis_fase6.py) consulta MongoDB y regenera automáticamente tablas, CSV/JSON, siete SVG e informe HTML. |
| RA4 — Indicadores | **10/10** | Se documentan diez indicadores distintos con fuente, unidad y periodo; combinan varias fuentes. Las cifras de Pisos.com llevan tamaño muestral y los estados Etxebide no publicados no se convierten en cero. |
| RA4 — Respuesta al reto | **7/10** | Se comparan Vitoria-Gasteiz, Bilbao y Donostia con indicadores calculados desde MongoDB. La comparación salarial juvenil es regional; no hay ingresos juveniles municipales verificados, así que no permite afirmar una tasa municipal real de emancipación. |
| RA4 — Preparación para visualización | **10/10** | La ejecución genera automáticamente conjuntos distintos, entre ellos `indicadores_municipales.csv`, `comparacion_tres_capitales.csv`, `renta_vs_alquiler_oferta.csv`, JSON y siete SVG. |

## Resumen estimado por bloques oficiales

| Bloque oficial | Suma estimada | Media por criterio |
|---|---:|---:|
| BDA RA1 | 37/40 | 9,25/10 |
| SBD RA3 | 40/40 | 10/10 |
| SBD RA4 | 37/40 | 9,25/10 |
| Total aritmético, si todos los criterios pesaran igual | 114/120 | 9,5/10 |

La rúbrica no especifica aquí una ponderación global entre criterios. El total
aritmético es solo una referencia del equipo y no una nota definitiva. Las
20 pruebas automatizadas pasaron en esta revisión, incluida la prueba de
integración real de atomicidad con MongoDB. El dry-run del importador genérico
terminó con código 0, sin escritura; descubrió 319 archivos y enruta EMAL y
Eustat de forma consistente, excluyendo los informes. Para repetir las pruebas:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```
