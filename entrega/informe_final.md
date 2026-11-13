# Informe final

## Resumen ejecutivo

El proyecto integra datos municipales de vivienda y contexto económico en
MongoDB, ejecuta consultas y agregaciones con PyMongo y genera tablas y gráficos
para comparar municipios de Euskadi. También se verificó un flujo de
reproducción de anuncios desde HDFS, a través de Kafka, hasta una colección
MongoDB separada.

Los datos permiten comparar precios de oferta, alquiler registrado, anuncios,
renta personal y demanda de vivienda protegida. Fase 6 incluye tanto un
escenario con remuneración juvenil regional como un cruce municipal entre
alquileres EMAL y la categoría Eustat «Renta del trabajo». Este último aporta
contexto económico local, pero no es salario neto ni está desglosado por edad;
ninguno de esos cocientes mide directamente la capacidad de emancipación de
una persona joven.

## Fuentes y conjuntos integrados

| Fuente | Datos usados | Cobertura/periodo | Significado y cautelas |
|---|---|---|---|
| Índice Inmobiliario Fotocasa | 41.164 observaciones | 251 municipios; 82 meses por serie; 2020-01 a 2026-10 | Oferta de alquiler (EUR/m²/mes) y compraventa (EUR/m²). |
| Pisos.com | 1.041 anuncios | Venta y alquiler; 1.040 con código municipal validado | Anuncios individuales. Para alquiler, el análisis usa 186 anuncios con precio/m² en 29 municipios y comunica los tamaños muestrales. |
| EMAL | 872 observaciones | 728 anual (73 municipios) y 144 vigentes (72 municipios); 71 municipios con valor anual comparable en 2024 | Alquiler registrado. La hoja fuente se refiere a municipios de más de 5.000 habitantes; la media anual corresponde a contratos iniciados ese año, no es precio de oferta. |
| Eustat | 247.212 observaciones en la colección canónica | 252 municipios; renta personal disponible y «Renta del trabajo» para 2024 | Magnitudes de renta personal anual (EUR/persona/año); la renta del trabajo municipal no tiene desglose por edad ni equivale a salario neto. |
| Etxebide | 16.170 filas en dos fotografías | Abril y julio de 2026; 245 municipios por fotografía | Demanda de vivienda protegida. Los valores suprimidos no se sustituyen por cero ni se extrapolan. |
| Encuesta de Condiciones de Trabajo | Fuente regional consultada desde `reto_vivienda.salarios` | Euskadi; remuneración 2024, edades 16-29 | Referencia neta mensual por sexo de personas asalariadas y asimiladas; no es salario municipal ni de toda la juventud. |
| IOVJ empleo-económico | Fuente regional consultada desde `reto_vivienda.indicadores_laborales` | Euskadi; indicador de 2024 | El valor 1.381 del grupo 18-29 se presenta como referencia separada, no se mezcla con la serie anterior. |

### Referencias salariales juveniles disponibles

Los archivos de `DatosAlvaro/Salario` sí aportan contexto económico juvenil,
pero su nivel geográfico no es municipal:

- `remuMedia.csv` describe la remuneración neta media del último mes cobrado
  por personas asalariadas y asimiladas de la C.A. de Euskadi. En 2024 registra
  1.612 EUR para hombres de 16-29 años y 1.545 EUR para mujeres de 16-29 años.
  Los valores están expresados a precios de 2024. Es un promedio regional, no
  el ingreso de toda la juventud ni una cifra por municipio. Esta fuente se usa
  para el escenario comparativo de esfuerzo.
- `iovj-empleo-economico.csv` registra para 2024 un salario neto mensual medio
  de 1.381 EUR para el grupo de 18-29 años. La tabla también presenta categorías
  de sexo y TTHH por separado; el valor 18-29 se usa solo como referencia
  adicional y no se combina con `remuMedia`, que tiene otro grupo de edad y
  definición.
- Ese mismo CSV incluye una renta personal media anual de 20.109 EUR para
  jóvenes de 25-29 años en 2024. Es renta personal, no salario.
- `salAnual.json` contiene salarios brutos anuales por edad para el conjunto
  nacional; `salario-ccaa.json` ofrece salario bruto medio por comunidad
  autónoma, pero sin desglose juvenil.

Estas fuentes son útiles para describir Euskadi o el contexto nacional, siempre
respetando su definición y población. La razón calculada en Fase 6 es un
escenario de precio municipal frente a ingreso regional; no asigna esos ingresos
a los municipios ni equivale al esfuerzo observado de una persona concreta.
Además, el cruce municipal usa la categoría Eustat «Renta del trabajo» de 2024
(EUR/persona/año) y el alquiler mensual medio EMAL de contratos iniciados en
2024. Esa renta personal municipal no tiene desglose por edad y no debe
llamarse salario juvenil. `salAnual.json` se conserva como contexto nacional y
no entra en los cálculos municipales.

El catálogo maestro contiene 252 municipios. Los códigos de municipio se
almacenan como cadenas de cinco caracteres. El único anuncio Pisos.com sin
código municipal válido se conserva sin asignarle uno.

### Investigación específica de ingresos juveniles municipales Eustat

Se revisó el catálogo completo de Eustat (2.039 tablas), los ocho JSON
originales de `DatosIker/originales`, los procesados y los scripts de descarga,
exploración y validación. También se consultaron metadatos y datos candidatos
en la API oficial. La respuesta municipal completa de RP11S coincide con el
JSON original y se contrastaron filas procesadas de las tres capitales.

La tabla RP03 (`PX_173402_crpf_rpf_rp03.px`) ofrece renta personal media
**anual** por edad para Euskadi, con periodos 2001, 2003, 2006, 2009, 2011 y
2013–2024. Incluye los grupos 18–19, 20–24 y 25–29, pero no 16–17 ni municipio.
RP11S (`PX_173402_crpf_rpf_rp11s.px`) incluye 252 códigos municipales del
catálogo del proyecto y periodos hasta 2024, pero no edad. Se comprobó que
ambas tablas no pueden combinarse para obtener renta juvenil municipal. No se
aplican a los municipios ingresos regionales ni repartos estimados.

En RP03, los valores de 2024 para el total de sexos son, por ejemplo, 1.599 EUR
de renta total y 1.077 EUR de renta del trabajo para 18–19 años; 8.156 y 7.097
EUR para 20–24; 20.109 y 18.005 EUR para 25–29. Son valores regionales de renta
personal anual, no salarios netos ni una media municipal del grupo 18–29.
RP11S tiene 357 valores nulos con marcas de estado `-` o `:`; al no disponer
de una glosa verificable para interpretarlas, se conservan como ausentes y no
se convierten en ceros ni se atribuyen a supresión.

**Conclusión:** no hay ingresos juveniles municipales verificados en las tablas
de Eustat examinadas y no se calcula un indicador municipal de esfuerzo juvenil
con ellas. Se mantienen por separado la remuneración juvenil neta regional,
la renta personal municipal y la renta municipal procedente del trabajo. El
detalle de tablas candidatas, cobertura, validaciones y valores ausentes está
en el [informe de investigación Eustat](../DatosIker/informes/investigacion_ingresos_juveniles_eustat.txt).

## Obtención, procesamiento y uso de las fuentes

El proyecto conserva scripts Python para automatizar el scraping de anuncios
Pisos.com y para consultar páginas Fotocasa y extraer las series del HTML
guardado. También existen clientes para consultar la API estadística oficial
de Eustat, como parte de la investigación y descarga de datos económicos.
Esto no es una API de precios inmobiliarios: los precios de vivienda del
proyecto se obtuvieron mediante scraping/series archivadas y no se implementó
un proveedor inmobiliario mediante API. La matriz valora esta distinción sin
afirmar que no exista ninguna llamada API.

Para publicar resultados Fotocasa, citar «Índice Inmobiliario Fotocasa» y
respetar la autorización académica y los límites de frecuencia comunicados. La
evidencia privada de autorización no se adjunta a este paquete de entrega.

## Modelo y recorrido de datos

La base aislada `reto_vivienda_fase3` tiene seis colecciones canónicas:

| Colección | Documentos | Uso |
|---|---:|---|
| `municipios` | 252 | Catálogo y metadatos municipales. |
| `precios_fotocasa` | 41.164 | Series de oferta por municipio, tipo y mes. |
| `anuncios_pisoscom` | 1.041 | Anuncios individuales. |
| `alquiler_emal` | 872 | Observaciones anual y vigente, diferenciadas. |
| `renta_personal_eustat` | 247.212 | Observaciones originales de renta personal. |
| `demanda_vpo` | 16.170 | Fotografías de demanda, valores y estados anidados. |

La relación entre las colecciones se realiza mediante `municipio_codigo`, que
referencia `municipios._id`. Se embeben únicamente los metadatos pequeños del
catálogo y se referencian las observaciones para evitar repetir el documento
municipal en cientos de miles de filas. Las fuentes permanecen en colecciones
separadas porque miden conceptos distintos. El flujo Kafka agrega una séptima
colección independiente, `anuncios_stream_fase5`, para no alterar la colección
canónica.

El diagrama de [arquitectura](./arquitectura_reto1.svg) representa los dos
caminos comprobados: la carga canónica desde los ficheros procesados y el replay
histórico HDFS → Kafka → MongoDB. HDFS mantiene separados 269 originales
(136.091.377 bytes) y 21 archivos procesados (205.376.874 bytes); los 21
procesados se verificaron por tamaño y SHA-256. Fase 6 consulta el ingreso
regional en una base separada mediante el cargador focalizado
[`cargar_salarios_regionales.py`](../src/cargar_salarios_regionales.py).

## Resultados principales

### Comparación de las capitales

| Municipio | Fotocasa alquiler, 2026-10 (EUR/m²/mes) | EMAL vigente, 2026-03-31 (EUR/m²/mes) | Mediana de alquiler Pisos.com (EUR/m²/mes; n) | Renta personal Eustat, 2024 (EUR/persona/año) |
|---|---:|---:|---:|---:|
| Vitoria-Gasteiz | 12,76 | 9,728 | 17,60 (n=1) | 22.514 |
| Bilbao | 16,87 | 12,202 | 19,33 (n=85) | 23.391 |
| Donostia / San Sebastián | 18,44 | 14,094 | 22,22 (n=12) | 27.389 |

La comparación Fotocasa–EMAL es descriptiva: las fuentes tienen metodologías y
fechas distintas. La mediana de Pisos.com en Vitoria se basa en un solo anuncio
y no es representativa. Eustat se presenta como renta personal disponible, no
como capacidad salarial de una persona joven.

### Evolución de la oferta Fotocasa

La serie disponible para las capitales contiene 82 meses por municipio, desde
enero de 2020 hasta octubre de 2026. La variación nominal documentada en Fase 4
fue:

| Municipio | Enero 2020 (EUR/m²) | Octubre 2026 (EUR/m²) | Variación nominal |
|---|---:|---:|---:|
| Vitoria-Gasteiz | 10,38 | 12,76 | +22,93 % |
| Bilbao | 16,67 | 16,87 | +1,20 % |
| Donostia / San Sebastián | 17,17 | 18,44 | +7,40 % |

La variación no está ajustada por inflación y refleja precios de oferta, no
necesariamente rentas efectivamente pagadas.

### Escenario de alquiler frente a remuneración juvenil regional

Se promediaron los 12 valores mensuales Fotocasa de 2024 por municipio y se
estimó el alquiler de una vivienda de 60 m². El coste mensual se dividió por la
remuneración neta mensual media regional de personas asalariadas y asimiladas
de 16-29 años, por sexo:

| Capital | Alquiler Fotocasa medio 2024 (EUR/m²/mes) | Alquiler estimado 60 m² (EUR/mes) | Referencia hombres 16-29 | Referencia mujeres 16-29 |
|---|---:|---:|---:|---:|
| Vitoria-Gasteiz | 11,829 | 709,75 | 44,03 % | 45,94 % |
| Bilbao | 15,557 | 933,45 | 57,91 % | 60,42 % |
| Donostia / San Sebastián | 18,664 | 1.119,85 | 69,47 % | 72,48 % |

Es un escenario explícito con ingreso regional, no un salario asignado a cada
municipio. Supone que una persona asume todo el alquiler y no incluye gastos,
vivienda compartida ni diferencias individuales de ingresos. IOVJ publica una
referencia distinta para 18-29 años (1.381 en 2024); no se mezcla con
`remuMedia` por las diferencias de edad y definición.

### Comparación municipal de renta del trabajo Eustat y alquiler EMAL

Se cruzaron por código municipal los datos de Eustat de 2024 para «Renta del
trabajo» y la renta mensual media EMAL de contratos iniciados en 2024. El
indicador anualiza la renta de alquiler EMAL por 12 y la expresa como porcentaje
de la renta personal media anual del trabajo. Hay datos válidos en **71
municipios**; la tabla completa se genera en
[`esfuerzo_alquiler_renta_trabajo_municipal_2024.csv`](../resultados/fase6/esfuerzo_alquiler_renta_trabajo_municipal_2024.csv).

| Municipio | Eustat renta personal del trabajo (EUR/persona/año) | EMAL renta media (EUR/mes) | Alquiler anualizado / renta del trabajo |
|---|---:|---:|---:|
| Vitoria-Gasteiz | 15.945 | 781,98 | 58,85 % |
| Bilbao | 16.040 | 910,66 | 68,13 % |
| Donostia / San Sebastián | 18.009 | 1.121,71 | 74,74 % |

En los 71 municipios con datos cruzables, el cociente más bajo es Lazkao
(38,62 %) y el más alto Donostia / San Sebastián (74,74 %). Son comparaciones
entre medias municipales de dos fuentes y no una tasa de esfuerzo real de los
hogares. La renta Eustat incluye todos los grupos de edad de la tabla y no es
salario neto juvenil; EMAL representa alquiler registrado de contratos
iniciados en el año. Se validó que los 71 valores EMAL utilizados coinciden con
la hoja T2.2 del Excel original.

La serie Fotocasa tiene además una limitación de granularidad: entre 251
códigos municipales hay 20 trayectorias históricas distintas; 235 códigos
comparten una de cuatro trayectorias repetidas. Por eso se marca esa
duplicación en el CSV de esfuerzo y el ranking limita la comparación a series
no compartidas. Las tres capitales mostradas tienen series propias en el
conjunto.

### Respuesta a la pregunta del reto

Los indicadores disponibles no permiten afirmar que una persona joven pueda
independizarse en cualquier municipio: falta una renta juvenil municipal
observada y comparable. Sí muestran que, bajo el supuesto explícito de una
persona que paga una vivienda de 60 m², el alquiler medio de oferta de 2024 en
las tres capitales equivale aproximadamente al 44–69 % de la referencia neta
regional masculina de 16–29 años y al 46–72 % de la femenina. Donostia presenta
el mayor porcentaje de ese escenario y Vitoria-Gasteiz el menor. Son cocientes
ilustrativos con precio municipal e ingreso regional, no porcentajes reales
observados de jóvenes ni una conclusión causal. La renta Eustat municipal de
todos los grupos de edad permanece como indicador contextual independiente.

### Demanda de vivienda protegida

En la fotografía Etxebide de 2026-07-01, la categoría de menores de 36 años
incluye 245 municipios: 127 con valor publicado y 118 con total suprimido/no
publicado. Los valores visibles no constituyen un total completo de demanda.

## Consultas, transformaciones y visualizaciones

- Cinco consultas MongoDB y tres Aggregation Pipelines ejecutados; incluyen
  filtros compuestos, proyecciones, ordenaciones, campos anidados y etapas
  como `$group`, `$lookup` y `$unwind`.
- El índice de consulta Fotocasa se contrastó con `explain()`: el plan de
  control recorrió 41.164 documentos (`COLLSCAN`) y el plan indexado examinó 10
  documentos y 10 claves (`IXSCAN`), devolviendo los mismos 10 resultados.
- Las cargas canónicas emplean upserts idempotentes, validación de claves
  naturales y campos de procedencia. La demostración CRUD inserta, consulta,
  actualiza y elimina un documento temporal, verificando cada operación.
- Fase 6 genera siete gráficos SVG, CSV y JSON desde consultas PyMongo, más un
  informe HTML. Se incluyen el escenario salarial regional y el cruce municipal
  Eustat-EMAL de renta del trabajo.

El informe y los conjuntos de visualización están en
[`resultados/fase6`](../resultados/fase6/informe_fase6.html). El JSON de Fase 4
está en [`resultados/fase4`](../resultados/fase4/consultas_y_agregaciones.json).

## Conclusión y límites

En los datos de oferta de las tres capitales, Vitoria-Gasteiz muestra el menor
precio de alquiler Fotocasa y Donostia / San Sebastián el mayor en octubre de
2026. EMAL confirma un orden de precios distinto en nivel, pero con su propia
fecha y población de contratos. Los anuncios Pisos.com aportan contexto
individual, aunque su cobertura municipal es menor. El cruce municipal de 2024
también muestra una proporción más alta de alquiler anualizado frente a la renta
del trabajo en Donostia que en Bilbao y Vitoria-Gasteiz; esta referencia no es
juvenil.

Estos resultados permiten describir y comparar el mercado; no determinan por
sí solos la posibilidad de emancipación. El escenario regional muestra una
proporción elevada del ingreso neto medio para alquilar 60 m² en las capitales,
especialmente en Donostia; debe interpretarse junto a sus límites y a la
duplicación de series Fotocasa. No se afirma que todas las personas jóvenes
perciban ese salario ni se calcula una tasa individual o municipal observada.

## Trazabilidad

- [Diseño y carga MongoDB — Fase 3](../DatosIker/informes/diseno_carga_mongodb_fase3.txt)
- [Consultas, agregaciones e índices — Fase 4](../DatosIker/informes/consultas_agregaciones_fase4.txt)
- [Flujo HDFS, Kafka y MongoDB — Fase 5](../DatosIker/informes/flujo_hdfs_kafka_mongodb_fase5.txt)
- [Investigación de ingresos juveniles Eustat](../DatosIker/informes/investigacion_ingresos_juveniles_eustat.txt)
- [Análisis municipal — Fase 6](../resultados/fase6/informe_fase6.html)
- [Código de análisis Fase 6](../src/analisis_fase6.py)

## Fuentes, bibliografía y procedencia

- **Fotocasa:** Índice Inmobiliario Fotocasa. Se conservan las series y el
  catálogo municipal originales/procesados en `DatosIker`; citar la fuente y
  respetar las condiciones académicas y de frecuencia comunicadas.
- **Pisos.com:** anuncios individuales reunidos en
  `DatosIker/originales/pisoscom` y procesados en
  `DatosIker/procesados/pisoscom`. El replay de Fase 5 utiliza el snapshot
  `pisos_euskadi.csv`, no anuncios en tiempo real.
- **EMAL:** fichero institucional original
  `DatosIker/originales/EMAL.-Barrios-Municipios.-2016-2026_es.xlsx`.
- **Eustat:** catálogo y respuestas originales de
  `DatosIker/originales/eustat_*.json`; catálogo y tablas consultables en la
  [API oficial de Eustat](https://www.eustat.eus/bankupx/api/v1/es/DB/).
  Códigos, dimensiones y observaciones contrastados están descritos en el
  informe de investigación enlazado arriba.
- **Etxebide:** las dos fotografías CSV de
  `DatosIker/originales/etxebide` y sus versiones con códigos municipales en
  `DatosIker/procesados/etxebide`.
- **Referencias económicas regionales:** `remuMedia.csv` e
  `iovj-empleo-economico.csv` conservados en `DatosAlvaro/Salario`; se
  documentan como fuentes regionales, con sus grupos de edad, unidad y
  definición, sin atribuirlos a municipios.
- **Evaluación:** [rúbrica oficial del Reto 1](<../RETO 1Evaluacion SBD-BDA.pdf>).
