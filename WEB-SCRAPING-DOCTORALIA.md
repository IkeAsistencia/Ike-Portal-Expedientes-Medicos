# Viabilidad del web scraping a Doctoralia — Portal Promédico

Fecha: 2026-10-20
Autor: equipo de desarrollo del Portal Promédico
Estado: **no viable** — se implementó una alternativa legítima (DENUE del INEGI)

## 1. Qué se pidió y qué se evaluó

Se solicitó programar un web scraping a [Doctoralia México](https://www.doctoralia.com.mx/)
usando como parámetros de búsqueda **entidad/municipio** y **especialidad**, para
ampliar la cobertura del Directorio de Proveedores y poder ofrecer médicos
*fuera de la red* cuando el padrón contratado no tiene cobertura en una zona.

El objetivo de negocio es legítimo y está atendido (ver sección 7). Lo que este
documento sustenta es por qué **la vía del scraping a Doctoralia no lo es**.

Se evaluaron las tres rutas técnicas con las que se podría implementar:

| Ruta | Endpoint | Resultado |
|---|---|---|
| A | `GET /buscar?q=…&loc=…` (buscador con filtros) | Bloqueada por `robots.txt` y por los T&C |
| B | `GET /{especialidad}/{ciudad}` (ej. `/cardiologo/guadalajara`) | Permitida por `robots.txt`, **prohibida por los T&C** |
| C | `GET /api/…`, `GET /ajax/…` (APIs internas del sitio) | Bloqueadas por `robots.txt` y por los T&C |

## 2. Resumen de impedimentos

| # | Impedimento | Carácter | Bloquea |
|---|---|---|---|
| 1 | Términos y Condiciones: cláusula expresa anti-scraping | Contractual | **Sí, de forma absoluta** |
| 2 | Términos y Condiciones: prohibición de uso para producto competidor | Contractual | **Sí, de forma absoluta** |
| 3 | `robots.txt` bloquea el buscador y las APIs internas | Técnico / normativo | Sí (rutas A y C) |
| 4 | Tratamiento de datos personales de terceros | Legal — requiere Jurídico | Probablemente sí |
| 5 | Fragilidad técnica y costo de mantenimiento | Operativo | No, pero lo vuelve inviable en la práctica |
| 6 | El orden de resultados responde a planes de pago | Calidad del dato | No, pero contamina el directorio |

> Los impedimentos 1 y 2 son suficientes por sí solos. Aunque se resolvieran los
> demás (por ejemplo, respetando `robots.txt` y usando solo la ruta B), **el
> scraping seguiría estando prohibido por contrato**.

## 3. Impedimento principal: los Términos y Condiciones

Los T&C vigentes de Doctoralia México, S.A. de C.V. —**última actualización:
1 de septiembre de 2026**— incorporan una cláusula específica y explícita contra
el scraping, dentro de la sección *9. Nuestros derechos de propiedad intelectual*.

Cita literal:

> **Sin scraping, sin extracción automatizada y sin entrenamiento de IA.** El
> Usuario no podrá (i) acceder al Sitio por medios automatizados o no humanos
> (robots, scripts, rastreadores); (ii) indexar (web crawling), extraer (web
> scraping) o de otro modo recopilar datos o contenido de la totalidad o parte
> del Sitio; (iii) aplicar ingeniería inversa, descompilar o intentar derivar el
> código fuente, los modelos, los algoritmos, los sistemas o los componentes
> subyacentes del Sitio; o (iv) utilizar el Sitio, sus resultados o cualquier
> dato generado por él para desarrollar, entrenar o mejorar cualquier producto,
> servicio, modelo, algoritmo, sistema o inteligencia artificial que compita con
> nuestro Sitio.

*(Las negritas del encabezado de la cláusula son del original; el resto de la
cita es textual, sin énfasis añadido.)*

Cómo aplica a lo que se pidió, inciso por inciso:

- **(i)** Un scraper es, por definición, acceso por medios automatizados.
  Prohibido sin importar qué ruta o qué volumen se use.
- **(ii)** Recopilar el listado de médicos por entidad/municipio y especialidad
  es exactamente "extraer o de otro modo recopilar datos o contenido de… parte
  del Sitio".
- **(iv)** Es el inciso más delicado para este caso: el Portal Promédico
  mantiene un **directorio de médicos con agenda de citas**, que es
  funcionalmente lo mismo que ofrece Doctoralia. Usar sus datos para alimentarlo
  encuadra en "desarrollar o mejorar un producto o servicio que compita con
  nuestro Sitio". No es una lectura forzada: es el supuesto literal.

La misma sección refuerza la prohibición con dos elementos adicionales:

> Doctoralia se reserva expresamente sus derechos y se opone a cualquier minería
> de textos y datos del Sitio y de su contenido […]. Toda minería o recopilación
> de textos y datos, incluso por medios automatizados, está sujeta al
> consentimiento específico previo de Doctoralia, salvo cuando se realice
> exclusivamente con fines de investigación científica […].

Esta oposición expresa es relevante porque cierra la puerta a la excepción de
minería de textos y datos: el único supuesto que se salva es la investigación
científica, que no es nuestro caso (uso comercial).

Y sobre las consecuencias económicas del incumplimiento, la misma sección
establece una obligación de indemnidad:

> Indemnizarás y eximirás a Doctoralia de toda responsabilidad por pérdidas,
> daños, costos, gastos (incluidos honorarios, costos y gastos legales),
> intereses, reclamaciones y responsabilidades, de cualquier tipo, derivados o
> relacionados con el incumplimiento por tu parte de esta sección.

Adicionalmente, la sección *5. Lo que no puede hacer con nuestro Sitio*
establece en **5.1** el compromiso de no "violar estos términos, cualquiera de
nuestras políticas aplicables a ti o cualquier ley o regulación aplicable", y en
**5.6** el de no hacer "un uso de nuestros Servicios distinto del previsto".

### 3.1 Por qué no sirve el argumento de "es información pública"

Que un dato sea visible sin registro no lo vuelve de libre aprovechamiento. Son
dos cosas distintas:

- **Visibilidad**: cualquiera puede consultar un perfil desde un navegador.
- **Licencia de uso**: los T&C definen *para qué* se puede usar lo que se ve.
  Aquí la limitan a "la recepción de Nuestros Servicios" y prohíben la
  extracción automatizada y la reutilización.

El contenido además está declarado como propiedad intelectual de Doctoralia o de
sus licenciantes, con prohibición expresa de reproducirlo, descargarlo,
extraerlo, reorganizarlo o crear trabajos derivados sin autorización escrita.
Un directorio propio construido con esos registros es, precisamente, un trabajo
derivado.

## 4. `robots.txt`: qué bloquea y qué no

Verificado el **2026-10-20** en `https://www.doctoralia.com.mx/robots.txt`.

Para `User-agent: *` (es decir, para cualquier cliente automatizado, incluido el
nuestro) están deshabilitadas, entre otras:

```
Disallow: /buscar?
Disallow: /api/
Disallow: /ajax/
Disallow: /ajax.php
Disallow: /*ranking-de-medicos*
Disallow: /anade-opinion/*
Disallow: /edit-opinion/
Disallow: /registro-medico
Disallow: /doctor-add
```

Consecuencia directa: **la ruta A (`/buscar?`) y la ruta C (APIs internas)
quedan descartadas**, y son justamente las que permitirían filtrar por
entidad/municipio y especialidad de forma estructurada, que es como se pidió.

### 4.1 Precisión importante, para no sobreafirmar

`robots.txt` **no** bloquea las URLs de listado por especialidad y ciudad
(ruta B). Se comprobó que `https://www.doctoralia.com.mx/cardiologo/guadalajara`
responde y no coincide con ninguna regla `Disallow`.

Es decir: **`robots.txt` por sí solo no resuelve el caso**. Si el análisis se
quedara ahí, alguien podría concluir —con razón— que la ruta B es scrapeable.
Lo que la impide es la cláusula contractual de la sección 3, que aplica a todo
el Sitio y a cualquier medio automatizado, con independencia de lo que permita
`robots.txt`.

Dicho de otro modo: `robots.txt` es una señal técnica; los T&C son una
obligación contractual. Cumplir la primera no exime de la segunda.

## 5. Datos personales de terceros

⚠️ **Esta sección requiere validación del área Jurídica / de Privacidad.** Aquí
solo se documenta la naturaleza del dato, que es lo que el equipo técnico puede
afirmar.

Lo que se extraería no son datos de establecimientos anónimos, sino de **personas
físicas identificadas**:

- Nombre completo del profesional de la salud y su cédula profesional.
- Domicilio del consultorio, teléfonos y medios de contacto.
- Fotografía y, en muchos perfiles, **opiniones de pacientes** sobre su atención.

Dos consideraciones:

1. Las opiniones de pacientes se refieren a atención médica recibida; el dato
   asociado puede tener una naturaleza más delicada que un simple directorio.
2. Nosotros no tenemos relación con esos profesionales ni base para tratar sus
   datos: no se dieron de alta con nosotros, no nos los proporcionaron y no
   recibirían nuestro aviso de privacidad.

Incorporarlos al padrón del portal implicaría tratarlos como propios sin
sustento. **Jurídico debe confirmar el encuadre y las obligaciones aplicables
antes de cualquier tratamiento de este tipo**; el equipo técnico no está en
posición de emitir esa conclusión.

Nota adicional: el Portal Promédico ya maneja expedientes médicos, por lo que
cualquier incidente de privacidad en este frente tendría un impacto reputacional
mayor que el de un directorio cualquiera.

## 6. Viabilidad técnica y de operación

Aun ignorando los impedimentos 1 a 4 —que no se pueden ignorar—, la solución
sería frágil:

- **Sin contrato de interfaz.** Un scraper depende de la maquetación HTML. Un
  rediseño, un cambio de clase CSS o un ajuste de etiquetas lo rompe sin aviso
  y sin versionado. Se convierte en una dependencia que falla en silencio.
- **El sitio administra activamente el acceso automatizado.** Su `robots.txt`
  no solo restringe rutas: fija `Crawl-Delay` para rastreadores conocidos
  (`AhrefsBot`, `bingbot`) y **veta por nombre** a varios bots
  (`Sogou web spider`, `spbot`, `MLBot`, `PiplBot`, `petalbot`, `neticle.hu`).
  Es decir, el acceso por bots se vigila y se filtra caso por caso. Si en algún
  momento nuestro agente fuera bloqueado, sostener la extracción exigiría
  disfrazarlo (rotación de IPs, user-agents falsos), lo que **agrava** el
  incumplimiento en vez de mitigarlo: dejaría de ser un acceso automatizado y
  pasaría a ser una elusión deliberada de controles.
- **Costo recurrente.** El mantenimiento no es puntual sino permanente, y cada
  falla se manifiesta como un directorio incompleto justo cuando se necesita
  cobertura.
- **Sin trazabilidad del dato.** No habría forma de acreditar de dónde salió
  cada registro ni cuándo se actualizó, lo que choca con el control que el
  portal necesita sobre su padrón.

## 7. Qué se implementó en su lugar

Para cubrir el objetivo real —ofrecer candidatos cuando la red no tiene
cobertura— se integró el **DENUE del INEGI** (Directorio Estadístico Nacional de
Unidades Económicas), entregado en el commit `cce6580`.

| Criterio | Scraping a Doctoralia | DENUE (INEGI) |
|---|---|---|
| Permiso de uso | Prohibido por T&C | API oficial, pública y gratuita |
| Contrato de interfaz | Ninguno (HTML) | API versionada y documentada |
| Naturaleza del dato | Personas identificadas + opiniones | Unidades económicas (establecimientos) |
| Exposición de datos personales | Alta | Mínima |
| Trazabilidad | Nula | Fuente citable y auditable |
| Mantenimiento | Permanente y reactivo | Estable |

Dónde vive: `app/services/denue_service.py` y el endpoint
`GET /directorio-proveedores/fuera-de-red`.

Cómo se diseñó para no repetir el problema de fondo:

- **No se guarda nada.** Cada búsqueda consulta en vivo al INEGI; no se
  construye una base derivada.
- **Un candidato no es un proveedor.** La pantalla lo deja explícito: no tienen
  clave, no se les puede agendar y no entran al padrón. Para incorporar a uno
  hay que darlo de alta por "Alta de médico", con validación de cédula y
  aprobación de un Administrador.

**Limitación conocida y declarada en la interfaz:** el DENUE clasifica por
*tipo de consultorio*, no por especialidad médica. Cardiología, pediatría,
dermatología y las demás comparten la clase `621113 Consultorios de medicina
especializada`, así que no es posible pedir una sola especialidad. Sí tienen
clase propia: odontología, psicología, nutrición, optometría, quiropráctica,
audiología/terapia y medicina general. La pantalla avisa qué tipo se consultó y
que hay que confirmar la especialidad al contactar al consultorio.

## 8. Calidad del dato: el orden de Doctoralia es comercial

Un punto que suele pasarse por alto y que, por sí mismo, desaconseja usar ese
listado como fuente de un directorio de proveedores.

El propio sitio declara que la posición en la que aparece un médico responde,
entre otros factores, a **su plan de suscripción**. Texto mostrado en el listado
de `/cardiologo/guadalajara`, verificado el 2026-10-20:

> Este especialista concuerda con los filtros que seleccionaste, aparece en la
> primera opción debido a su disponibilidad, calificaciones, completitud de
> perfil y su plan de suscripción.

Importar ese orden significaría trasladar al Portal Promédico el sesgo de pago
de otra plataforma, presentándolo al usuario como si fuera un criterio de
cobertura o de idoneidad clínica. Para una red de proveedores donde el orden
debería responder a convenio, tarifa y disponibilidad real, es un defecto de
origen.

## 9. Alternativas legítimas, si se quiere esa cobertura

Si el interés es específicamente el padrón de Doctoralia o un dato equivalente
al suyo:

1. **Convenio comercial con Doctoralia / Docplanner.** Es la vía que los propios
   T&C contemplan: "salvo que Nosotros lo autoricemos expresamente por escrito"
   y "sujeta al consentimiento específico previo". Si el dato vale lo que
   estimamos, conviene negociarlo y obtener de paso un SLA y un contrato de
   interfaz.
2. **Catálogo CLUES (Secretaría de Salud).** Descarga oficial de
   establecimientos de salud. Se evaluó con el archivo real: ver sección 10.
3. **Registro Nacional de Profesionistas (SEP).** Fuente oficial para validar
   cédulas, que además es un pendiente real del proyecto: hoy la validación de
   cédula sigue simulada.
4. **Google Maps Platform (Geocoding / Places).** Permite el uso programático,
   pero con restricciones fuertes de almacenamiento y de con qué mapa se puede
   mostrar. Se evaluó a detalle en la sección 11.
5. **Alta directa de proveedores.** La vía que ya opera: el propio médico se
   registra, se valida su cédula y un Administrador lo aprueba. Es la única que
   produce un proveedor realmente contratable, con tarifa y convenio acordados.

## 10. Evaluación del Catálogo CLUES (medida con el archivo real)

Surgió al buscar una fuente que cubriera el mismo objetivo sin scraping. Se
descargó y analizó el archivo completo el **2026-10-20** para no opinar sobre
supuestos.

**Qué es:** el Catálogo de Clave Única de Establecimientos de Salud, que publica
la Dirección General de Información en Salud (DGIS) de la Secretaría de Salud.

| Dato | Valor |
|---|---|
| Archivo | `ESTABLECIMIENTO_SALUD_202608.xlsx` (25.3 MB), corte 2026-08, publicado 2026-09-23 |
| Hojas | `CLUES_202608`, `SUBCLUES_202608`, `HORARIOS_202608` |
| Registros | 64,450 establecimientos, 68 columnas |
| Acceso | Descarga directa, sin token ni scraping |

### 10.1 Lo que sí aporta

De los 64,450 registros, **19,077 son "SERVICIOS MEDICOS PRIVADOS"** y de esos
**17,307 están EN OPERACION** — que es el universo que nos interesa.

Completitud de ese universo, contra los campos que usa nuestro padrón:

| Campo del padrón | Cobertura en CLUES |
|---|---|
| Nombre y nombre comercial | 100 % |
| Estado y municipio | 100 % |
| Calle y número exterior | ~100 % |
| Colonia | 98.9 % |
| Código postal | 99.9 % |
| RFC | 96.2 % |
| **Latitud / longitud** | **92.4 %** |
| Teléfono | 82.8 % |

Alcance geográfico: **32 entidades y 1,167 municipios**.

Dos cosas que encajan sin trabajo extra:

- **Las claves son las del INEGI** (`01`…`32` para entidad, `001`… para
  municipio), el mismo formato que ya usamos en la búsqueda del DENUE. Se cruza
  con el catálogo de entidades del portal sin inventar equivalencias.
- **Es un `.xlsx` y el portal ya sabe leer `.xlsx`**: el cargador del padrón lo
  ingeriría con cambios acotados al mapeo de columnas.

El dato más valioso son las **coordenadas**: el Excel que validó el área trae
`Latitud Consultorio*` y `Longitud Consultorio*` **vacías en las 662 filas**, y
CLUES las tiene en el 92.4 % de sus registros privados.

### 10.2 Lo que NO aporta (y por qué no sustituye lo que se pidió)

Aquí está lo importante, y conviene decirlo antes de que alguien se entusiasme
con los 17,307 registros:

1. **CLUES no trae especialidad médica.** De los 11,976 consultorios privados en
   operación, **el 100 % tiene la subtipología en `NO ESPECIFICADO`**. Es
   exactamente la misma limitación que el DENUE: sirve para saber que ahí hay un
   establecimiento de salud, no para pedir "cardiólogos".
2. **La mayoría no son consultorios de especialidad.** Desglose por tipología de
   los 17,307 privados en operación:

   | Tipología | Registros |
   |---|---|
   | Consultorio adyacente a farmacia | 11,240 |
   | No especificado | 4,341 |
   | Consultorio particular | 736 |
   | Laboratorios | 519 |
   | Clínica | 304 |
   | Unidad móvil | 57 |
   | Resto (banco de sangre, almacenes, etc.) | 110 |

   Es decir, **el 65 % son consultorios de farmacia**. Para una red de
   especialistas, el subconjunto realmente aprovechable es mucho menor que la
   cifra bruta: 736 consultorios particulares, 304 clínicas y 3,669
   establecimientos de hospitalización.
3. **No contiene médicos, sino establecimientos.** No hay nombre de profesional
   ni cédula, así que no reemplaza la validación contra el RNP.

### 10.3 Cruce real contra nuestro padrón de 662

Se cruzó el archivo validado del área (662 proveedores) contra CLUES, para medir
cuánto enriquecería lo que ya tenemos. El resultado obliga a matizar:

| Criterio de cruce | Proveedores | Lectura |
|---|---|---|
| Empatan por RFC | 145 (21.9 %) | Cifra bruta, **no usable tal cual** |
| …de esos, con un solo establecimiento | 87 | El resto es ambiguo |
| …y además mismo municipio | 75 | Empate razonable |
| …apuntando a OTRO municipio | 12 | **Dato equivocado si se usa a ciegas** |
| Empatan con varios establecimientos | 58 | Requieren desempate |
| **Empates confiables (RFC + municipio + CP, con coordenadas)** | **73 (11 %)** | Lo que de verdad se puede enriquecer |

El matiz técnico que explica la diferencia: **el RFC en CLUES es de la persona
moral, no de la sucursal**. Hay 159 RFC con más de un establecimiento (hasta 8
en un caso), así que cruzar solo por RFC asignaría las coordenadas de *otra*
sucursal. Los 12 empates con municipio distinto son justamente ese error
materializado.

Por eso la cifra a considerar no es 22 % sino **11 %**, usando RFC + municipio +
código postal como criterio. Cruzar además por nombre normalizado agrega 16
proveedores más que no empataron por RFC.

### 10.4 Conclusión sobre CLUES

**No resuelve lo que motivó la solicitud original** (buscar por especialidad),
porque no tiene especialidad y dos tercios de su padrón privado son consultorios
de farmacia. Pero sí es un complemento legítimo y barato para tres cosas
concretas:

1. **Rellenar coordenadas** del padrón actual: ~11 % con criterio conservador, y
   el mapa del Directorio hoy no tiene con qué ubicar a nadie.
2. **Verificar que un establecimiento existe y está en operación** contra una
   fuente oficial, antes de contratarlo.
3. **Prospectar instituciones** (clínicas y hospitales privados) en zonas sin
   cobertura, como complemento del DENUE.

Recomendación: tratarlo como **fuente de enriquecimiento y verificación**, no
como fuente de alta de proveedores.

### 10.5 Implementado: enriquecimiento de coordenadas

Se implementó el punto 1 de esa recomendación.

- Lógica: `app/services/clues_service.py`
- Para correrlo: `python -m scripts.enriquecer_coordenadas_clues <archivo.xlsx>`

Arranca **en seco**: muestra qué haría y solo escribe si se le agrega
`--aplicar`. Reglas con las que se construyó:

- **Nunca pisa coordenadas existentes.** Las que vienen en el Excel del área
  son la fuente autorizada; aquí solo se llenan las vacías.
- **Todo cruce exige municipio y código postal**, además de RFC o nombre. Sin
  ese candado, el RFC (que en CLUES es de la persona moral) le asignaba a 12
  proveedores las coordenadas de un establecimiento de otro municipio.
- **Lo ambiguo se descarta.** Si una llave apunta a dos establecimientos, el
  proveedor se queda sin coordenadas: es preferible a ubicarlo mal.
- **Queda registrada la procedencia** en `proveedores.origen_coordenadas`
  (`carga` o `clues`), para saber qué auditar.
- **Una carga posterior no borra lo enriquecido.** El Excel entrega las
  coordenadas vacías y la carga es incremental, así que sin este cuidado la
  siguiente carga dejaba en NULL lo ya llenado.

Resultado sobre el padrón real (666 proveedores, 1 con coordenadas):

| | |
|---|---|
| Enriquecidos | **74** (73 por RFC + 1 por nombre) |
| Ubicables en el mapa ahora | **75 de 666** (11.3 %) |
| Sin coincidencia confiable | 591 |

Para el 89 % restante sigue haciendo falta que el área llene las columnas de
coordenadas del Excel (sección 11.6).

## 11. Google Maps / Places para el mapa del Directorio

Se evaluó aparte, a petición del usuario, porque es la otra vía que se suele
proponer para resolver lo mismo. Verificado el **2026-10-20** contra la
documentación y los términos vigentes.

### 11.1 El punto de partida: el mapa no está roto, está vacío

El mapa del Directorio ya funciona (Leaflet sobre teselas de Esri y
OpenStreetMap) y solo ubica a quien trae coordenadas reales. El problema es que
casi nadie las trae:

| Concepto | Cantidad |
|---|---|
| Proveedores en el padrón | 666 |
| **Con latitud y longitud** | **1** |
| Sin coordenadas | 665 |
| Con domicilio geocodificable (calle + CP) | 660 |

Las columnas `Latitud Consultorio*` y `Longitud Consultorio*` existen en el
layout que validó el área, pero vienen **vacías en las 662 filas**.

Por eso "usar el mapa con Google" son en realidad dos cosas distintas:

- **(A)** Cambiar la base del mapa (Leaflet -> Google Maps).
- **(B)** Usar Google para **obtener las coordenadas** que hoy faltan
  (Geocoding API o Places API).

Lo que haría falta de verdad es (B). Y como se ve abajo, (B) obliga a (A).

### 11.2 Lo que se necesita técnicamente

1. **Cuenta de facturación de Google Cloud y una API key.** La facturación es
   obligatoria aunque el consumo caiga en el tramo gratuito: sin ella las APIs
   no responden.
2. **Habilitar dos APIs:** *Maps JavaScript API* (mostrar el mapa) y
   *Geocoding API* (convertir domicilio en coordenadas).
3. **Restringir la key** por dominio (HTTP referrer) y fijar cuotas diarias en
   la consola, para que una fuga de la llave no se vuelva consumo.
4. **Publicar Términos de Uso y Aviso de Privacidad** que incorporen los de
   Google: es requisito explícito de la política de ambas APIs.
5. **Mostrar la atribución** de Google donde se despliegue su contenido.
6. **Migrar el mapa de Leaflet a Google Maps** (ver 11.3).

### 11.3 El impedimento real no es el costo, son los términos

Citas literales de los *Google Maps Platform Service Terms* vigentes:

> **6.2 No use with a non-Google map.** Customer must not use Google Maps
> Content from the Geocoding API in conjunction with a non-Google map.

Es decir: si las coordenadas se obtienen con Google, **no se pueden pintar en
el mapa actual** (Leaflet con teselas de OpenStreetMap/Esri). Tendría que ser
un mapa de Google. La misma restricción aplica a Places (cláusula 14.2).

Y sobre guardarlas, que es lo que el padrón necesita:

> **6.3.1** Customer may temporarily cache latitude (lat) and longitude (lng)
> values from the Geocoding API for up to **30 consecutive calendar days**,
> after which Customer must delete the cached latitude and longitude values.

> **6.3.2** Customer may indefinitely cache latitude (lat), longitude (lng),
> formatted_address, and the structured address values from the Geocoding API
> **solely to support the direct, End User facing functionality of the Customer
> Application that initiated the request** […]. **Cached data must be logically
> isolated to the specific End User it is associated with and must not be used
> across multiple End Users.**

La excepción de 6.3.2 **no nos aplica**: el padrón es un catálogo compartido
que consultan todas las personas de Cabina, no un dato aislado por usuario
final. Queda entonces la regla general:

> **No se pueden guardar de forma permanente en el padrón las coordenadas
> obtenidas de Google.** O se re-geocodifica cada 30 días o menos, o se
> geocodifica al vuelo cada vez que se abre el mapa.

Con Places es todavía más estricto: su política dice que el contenido **no se
puede almacenar**, y el único campo exento de esa restricción es el
`place_id`, que sí se puede guardar indefinidamente.

### 11.4 El costo, para dimensionarlo

A la escala de este portal el costo es prácticamente nulo, así que no es el
criterio de decisión:

- *Dynamic Maps* (cargas del mapa): **10,000 gratis al mes**, después 7.00 USD
  por cada 1,000.
- Geocodificar los 660 domicilios una sola vez cae dentro del tramo gratuito
  del SKU de Geocoding.
- El crédito mensual de 200 USD **ya no existe**: terminó el 28 de febrero de
  2025 y se reemplazó por topes gratuitos por SKU.

El problema es la obligación de borrar el dato, no pagarlo.

### 11.5 Qué implicaría en arquitectura, si se decidiera hacerlo

- Reescribir `frontend/js/directorio/mapa-zona.html` sobre el SDK de Google en
  vez de Leaflet.
- Un trabajo recurrente que re-geocodifique el padrón al menos cada 30 días, o
  geocodificar en cada apertura del mapa (más llamadas, más costo, más
  dependencia de que el servicio responda).
- Un campo que distinga las coordenadas "de Google" (borrables) de las propias
  (permanentes), porque no se pueden tratar igual.

### 11.6 Las alternativas que sí permiten conservar el dato

Tres fuentes dan coordenadas sin restricción de almacenamiento:

1. **La propia columna del Excel.** Ya existe en el layout y el cargador ya la
   lee. Si el área la llena, el mapa funciona sin costo, sin migración y sin
   obligación de borrar nada. Es la vía más barata de todas.
2. **CLUES** (sección 10): coordenadas oficiales en el 92.4 % de sus
   establecimientos privados.
3. **DENUE** (INEGI): ya integrado y **ya devuelve** latitud y longitud de los
   candidatos fuera de la red.

### 11.7 Conclusión sobre Google

Para solo pintar pines en un mapa, Google **cuesta más en restricciones que en
dinero**: obliga a cambiar la base del mapa y a borrar las coordenadas cada 30
días. La recomendación es pedir primero que el Excel del área traiga llenas sus
dos columnas de coordenadas, que es el mismo dato sin ninguna de esas
ataduras.

Google Maps se justifica si además se quiere Street View, rutas o autocompletado
de direcciones en el Alta de médico: ahí sí aporta algo que las fuentes
oficiales no dan.

## 12. Conclusión

El web scraping a Doctoralia **no es viable** y la recomendación es no
implementarlo. El impedimento no es técnico sino contractual, y es explícito:
los T&C vigentes desde el 1 de septiembre de 2026 prohíben el acceso
automatizado, la extracción de datos y —de forma directamente aplicable a este
proyecto— el uso de esos datos para alimentar un servicio que compita con el
suyo, con una obligación de indemnidad asociada al incumplimiento.

El objetivo de negocio que motivó la solicitud **ya está cubierto** con el DENUE
del INEGI, con una fuente oficial, sin almacenar datos personales de terceros y
sin depender de la maquetación de un sitio ajeno.

## Anexo A — Cómo reproducir las verificaciones

Todo lo citado aquí es verificable de forma independiente. Fecha de
comprobación: **2026-10-20**.

| Afirmación | Cómo comprobarla |
|---|---|
| `robots.txt` bloquea `/buscar?`, `/api/`, `/ajax/` | `curl https://www.doctoralia.com.mx/robots.txt` y buscar el bloque `User-agent: *` |
| Las URLs de especialidad/ciudad no están bloqueadas | Mismo archivo: no hay regla que cubra `/{especialidad}/{ciudad}` |
| El sitio veta bots por nombre y fija `Crawl-Delay` | Mismo archivo: bloques de `Sogou web spider`, `spbot`, `MLBot`, `PiplBot`, `petalbot`, `neticle.hu`, y `Crawl-Delay` para `AhrefsBot` y `bingbot` |
| Cláusula anti-scraping y fecha de los T&C | `https://www.doctoralia.com.mx/terminos-y-condiciones`, sección 9; el encabezado indica "Última actualización: 1 de septiembre de 2026" |
| Prohibiciones de la sección 5 | Mismo documento, sección "5. Lo que no puede hacer con nuestro Sitio" |
| El orden depende del plan de suscripción | Visitar `https://www.doctoralia.com.mx/cardiologo/guadalajara` y leer la nota del primer resultado |
| Existencia y contenido del Catálogo CLUES | `http://www.dgis.salud.gob.mx/contenidos/intercambio/clues_gobmx.html` → enlace "Establecimientos de Salud (Formato XLSX)" |
| Cifras de la sección 10 | Descargar ese `.xlsx` y agrupar la hoja `CLUES_202608` por `NOMBRE DE LA INSTITUCION`, `ESTATUS DE OPERACION` y `NOMBRE DE TIPOLOGIA` |
| Cláusulas 6.2, 6.3.1, 6.3.2 y 14.2 de Google | `https://cloud.google.com/maps-platform/terms/maps-service-terms`, secciones "6. Geocoding API" y "14. Places API" |
| Places no permite almacenar su contenido | `https://developers.google.com/maps/documentation/places/web-service/policies` |
| Tramo gratuito de 10,000 cargas de mapa | `https://developers.google.com/maps/billing-and-pricing/pricing`, tabla "Maps - loads", SKU Dynamic Maps |
| Proveedores sin coordenadas en el padrón | `SELECT COUNT(*) FROM proveedores WHERE latitud IS NULL OR longitud IS NULL` en la base SQLite del portal |

## Anexo B — Puntos que requieren validación de otras áreas

| Punto | Área | Por qué |
|---|---|---|
| Encuadre y obligaciones en materia de datos personales (sección 5) | Jurídico / Privacidad | El equipo técnico no puede emitir la conclusión legal; aquí solo se documenta la naturaleza del dato |
| Interés real en un convenio con Doctoralia / Docplanner | Negocio / Compras | Es la única vía que los T&C admiten para acceder a ese padrón |
| Alcance deseado de la validación contra el RNP (SEP) | Negocio | Hoy la validación de cédula del portal sigue simulada |
| Revisar los cruces de CLUES antes de confiar en ellos (sección 10.5) | Negocio | Son 74 y se pueden listar con `--detalle`. En algunos, el nombre del establecimiento en CLUES no se parece al del padrón aunque coincidan RFC, municipio y CP |
| Pedir al área que llene Latitud y Longitud en el Excel (sección 11) | Negocio | Es la vía más barata para que el mapa funcione: el dato ya cabe en el layout vigente y no tiene restricción de almacenamiento |
| Contratar o no Google Maps Platform (sección 11) | Negocio / Jurídico | Obliga a migrar el mapa y a borrar las coordenadas cada 30 días; solo se justifica si además se quiere Street View, rutas o autocompletado de direcciones |
