# Tarea: crear un sistema de importación y transformación de datos para MongoDB

Estoy desarrollando un proyecto académico de Big Data con Python y MongoDB cuyo objetivo es analizar si una persona joven puede independizarse en Euskadi con su salario.

Quiero que analices el proyecto existente y desarrolles un sistema reutilizable que lea todos los archivos de las carpetas `DatosAkira/, DatosAlvaro/, DatosIker/`, procese sus datos y los prepare para almacenarlos en MongoDB. Debes adaptar la solución a los archivos reales que encuentres, no asumir que todos los CSV tienen la misma estructura. No leas los scripts de extraccion de datos, solo archivos de datos.

## 1. Antes de programar: analiza los datos

Inspecciona todos los archivos de las carpetas `DatosAkira/, DatosAlvaro/, DatosIker/` y sus subcarpetas, si existen.

Identifica y analiza:
- CSV con diferentes separadores, codificaciones, encabezados y formatos numéricos.
- JSON, incluyendo estructuras anidadas y listas de objetos.
- Excel, XLSX y XLSM, incluyendo hojas múltiples, encabezados desplazados, celdas vacías y tablas de datos.
- Otros formatos de datos que encuentres y que puedas procesar razonablemente.

Para cada archivo, determina:
- Nombre y formato.
- Hojas, tablas o estructura interna cuando corresponda.
- Columnas y tipos de datos detectados.
- Número aproximado de filas o registros.
- Campos que representan municipios, territorios, fechas, periodos, salarios, precios de vivienda, población u otros indicadores.
- Valores ausentes, duplicados, columnas problemáticas y posibles inconsistencias.
- Si comparte estructura y finalidad con otros archivos.

No modifiques ni sobrescribas los archivos originales de `DatosAkira/, DatosAlvaro/, DatosIker/`.

Si algún archivo no puede procesarse, registra claramente el motivo y continúa con los demás.

## 2. Arquitectura que debes implementar

Trabaja sobre la estructura existente del proyecto. Debes escribir o actualizar exclusivamente estos tres archivos dentro de `src/`:

- `src/config.py`
- `src/importar_datos.py`
- `src/transformar.py`

No crees archivos adicionales sin mi autorización. Puedes leer otros archivos del proyecto para entender su estructura y dependencias.

### `src/config.py`

Debe centralizar:
- La configuración de MongoDB, utilizando una variable de entorno `MONGO_URI` y una URI local por defecto.
- El nombre de la base de datos, por defecto `reto_vivienda`.
- Las rutas de `DatosAkira/, DatosAlvaro/, DatosIker/` y las opciones generales de lectura.
- La configuración de los datasets que necesiten reglas específicas.
- Los mapeos de columnas y tipos de datos cuando sean necesarios.
- Las reglas de normalización y validación que deban compartirse entre módulos.

No inventes columnas ni asumas que un campo existe si no lo has comprobado en los archivos reales.

### `src/transformar.py`

Implementa funciones reutilizables para transformar los datos antes de cargarlos en MongoDB.

Debe incluir, cuando proceda:
- Normalización de nombres de columnas.
- Conversión de importes numéricos, incluidos formatos europeos como `1.234,56` y valores con símbolos monetarios.
- Conversión de fechas a objetos `datetime` compatibles con BSON.
- Conversión correcta de valores ausentes a `None`, sin convertirlos en cadenas como `"nan"`, `"None"` o `"NaN"`.
- Normalización de nombres de municipios y territorios sin destruir información original relevante.
- Tratamiento de espacios, caracteres especiales y encabezados duplicados.
- Validación de tipos y detección de valores incoherentes.
- Detección de registros duplicados cuando exista una clave razonable.
- Funciones específicas para datasets que realmente necesiten una transformación particular.

No conviertas indiscriminadamente todas las columnas a números o fechas. Respeta los identificadores, códigos postales, códigos municipales y otros valores que deban conservarse como texto.

Cuando un dato sea ambiguo o no pueda convertirse de forma segura, conserva el valor original cuando sea posible, registra el problema y evita inventar un valor.

No elimines registros automáticamente solo porque tengan campos vacíos. Aplica reglas de calidad justificadas según la finalidad de cada dataset.

### `src/importar_datos.py`

Implementa el proceso general de descubrimiento, lectura, transformación y carga en MongoDB.

Debe:
1. Descubrir automáticamente los archivos compatibles que haya en `DatosAkira/, DatosAlvaro/, DatosIker/` y sus subcarpetas.
2. Evitar procesar dos veces el mismo archivo si aparece por rutas duplicadas.
3. Detectar el formato y utilizar el lector adecuado.
4. Manejar CSV con distintos separadores y codificaciones habituales.
5. Procesar JSON con estructuras distintas, incluyendo listas de documentos y objetos anidados cuando sea posible.
6. Leer las hojas relevantes de Excel y los XLSM sin modificar los originales ni ejecutar macros.
7. Inspeccionar las estructuras y aplicar las reglas configuradas para cada dataset.
8. Transformar los registros mediante las funciones de `transformar.py`.
9. Elegir una colección MongoDB coherente con la entidad o el tipo de datos, y no simplemente crear una colección por cada archivo.
10. Registrar la procedencia de los datos, incluyendo archivo de origen y fecha de importación. Conserva las fechas de observación originales cuando existan.
11. Insertar los documentos por lotes utilizando operaciones eficientes como `insert_many()` o `bulk_write()` cuando proceda.
12. Mostrar estadísticas por archivo: registros leídos, insertados, actualizados, omitidos y errores.
13. Manejar excepciones por archivo para que un error no detenga toda la importación.
14. Cerrar correctamente la conexión con MongoDB.
15. Permitir ejecutar el proceso desde la raíz del proyecto mediante `python -m src.importar_datos` si la estructura existente lo permite, o documentar la forma correcta de ejecución sin modificar archivos adicionales.

## 3. Diseño de las colecciones

Analiza los datos reales y agrupa los registros por entidades coherentes.

Por ejemplo, podrían existir colecciones para:
- Viviendas en alquiler.
- Viviendas en venta.
- Salarios.
- Población.
- Demanda de vivienda protegida.
- Otros indicadores relevantes.

Estos son ejemplos, no una lista obligatoria. Decide el modelo final después de inspeccionar los datos.

Si varios archivos contienen el mismo tipo de información, valora consolidarlos en una misma colección cuando sus estructuras sean compatibles. Si sus diferencias son importantes, conserva colecciones separadas y explica por qué.

No mezcles datos de diferentes niveles geográficos, periodos o unidades sin identificarlos correctamente.

No calcules promedios ni agregues registros durante la importación si eso supone perder información original. Conserva los datos de origen y deja los análisis para las consultas y agregaciones posteriores.

Añade metadatos de procedencia sin sobrescribir campos originales. Evita colisiones con nombres de campos que ya existan en los archivos.

## 4. Evitar duplicados y permitir reejecuciones

El proceso debe ser lo más idempotente posible: ejecutar la importación varias veces no debe duplicar automáticamente todos los documentos.

- Investiga si existe un identificador único de origen.
- Si existe, utilízalo para identificar registros.
- Si no existe, evalúa una clave compuesta razonable basada en los campos reales.
- No asumas que dos viviendas con el mismo municipio y precio son duplicados.
- No sobrescribas silenciosamente datos diferentes.
- Si no se puede establecer una clave fiable, documenta la limitación y adopta una estrategia conservadora.
- Utiliza `upsert` o `bulk_write` cuando resulte apropiado.
- Crea índices únicos únicamente cuando la unicidad esté realmente garantizada.

No borres automáticamente colecciones ni documentos antes de importar.

## 5. Calidad de datos y trazabilidad

El sistema debe detectar, cuando corresponda:
- Columnas obligatorias ausentes.
- Campos vacíos.
- Tipos incorrectos.
- Importes negativos o imposibles.
- Fechas inválidas.
- Duplicados potenciales.
- Inconsistencias entre unidades y niveles geográficos.
- Registros que no pueden transformarse de manera fiable.

Distingue entre un error que impide importar un registro y una advertencia que permite conservarlo.

No ocultes errores ni descartes registros silenciosamente. Muestra un resumen claro de los problemas detectados y su archivo de origen.

No inventes datos para rellenar valores ausentes.

## 6. Requisitos técnicos

- Utiliza Python y PyMongo.
- Utiliza pandas cuando aporte valor.
- Utiliza librerías adicionales solo cuando sean necesarias para los formatos encontrados.
- Mantén el código organizado, modular, legible y documentado.
- No dupliques la lógica de transformación entre archivos.
- Utiliza `pathlib` para manejar rutas.
- No incluyas credenciales reales en el código.
- Evita cargar archivos enormes completos en memoria cuando puedas procesarlos por bloques.
- Respeta los nombres y las convenciones existentes en el proyecto.
- No modifiques ni sobrescribas archivos originales.
- No elimines datos ni colecciones existentes.

## 7. Pruebas y verificación

Antes de dar por terminada la tarea:

1. Comprueba la sintaxis de los tres archivos.
2. Verifica los imports y las rutas.
3. Prueba la lectura de cada tipo de archivo encontrado.
4. Prueba las transformaciones con ejemplos extraídos de los propios archivos.
5. Verifica el tratamiento de nulos, números europeos, fechas e identificadores.
6. Comprueba que un archivo incorrecto no detiene el procesamiento de los demás.
7. Comprueba la estrategia de duplicados.
8. Si hay una instancia MongoDB disponible, prueba la conexión y una importación controlada sin borrar datos existentes.
9. Si MongoDB no está disponible, realiza las pruebas que no requieran conexión e indica claramente las que no hayas podido completar.

No afirmes que una prueba se ha ejecutado correctamente si no la has ejecutado.

## 8. Resultado final

Cuando termines, proporciona:
- Los tres archivos implementados.
- Una explicación de qué colecciones has elegido y por qué.
- Una tabla con todos los archivos analizados, su estructura detectada y su destino en MongoDB.
- Las reglas de transformación específicas que has aplicado.
- Las limitaciones y los archivos que no hayas podido procesar.
- Las dependencias que deban instalarse.
- Los comandos exactos para ejecutar la importación desde la raíz del proyecto.
- Los resultados de las pruebas realmente ejecutadas.

Prioriza una solución robusta y comprensible para un proyecto académico. No añadas complejidad innecesaria y no te limites a crear un importador genérico que falle con las estructuras reales de mis archivos.

**Empieza inspeccionando el proyecto y todos los archivos de las carpetas `DatosAkira/, DatosAlvaro/, DatosIker/`. Después implementa los tres archivos y verifica el resultado. No te quedes únicamente en proponer una arquitectura o mostrar ejemplos: realiza los cambios en el código.**