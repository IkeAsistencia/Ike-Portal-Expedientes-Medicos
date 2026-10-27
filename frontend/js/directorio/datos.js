/* Directorio de Proveedores: datos de la pantalla.

   YA ESTÁ CONECTADO AL BACKEND:
     - Búsqueda y resultados: leen el padrón real (GET /directorio-proveedores),
       con los dos orígenes juntos -- "Dentro de la red" (llegó en el Excel
       oficial: tiene convenio con IKE) y "Fuera de la red" (aprobada en el
       portal, sin el proceso formal de convenio).
     - Alta de médico y sus solicitudes: se guardan de verdad; al aprobarse,
       el médico entra al padrón con su propia clave (PRV-000001).
     - Citas: se agendan contra esa clave y quedan registradas; los horarios
       libres los decide el servidor (GET /directorio-proveedores/{clave}/agenda),
       no un hash del navegador como antes.

   NO HAY DATOS SIMULADOS. Todo lo que se muestra sale del padrón real, del
   catálogo de especialidades o del catálogo de Entidad/Municipio. Con el
   portal recién desplegado (padrón vacío) las pantallas se ven vacías a
   propósito: es la verdad del sistema, no una falla.

   De la cédula profesional y el RFC solo se valida el formato; quien revisa
   las solicitudes los confirma en la SEP y el SAT (ver validacion-alta.js). */
import { api, apiArchivo } from "../core/api.js";
import { normalizarEntidad } from "../core/formato.js";
import { bloqueHorarioVacio, leerCosto, parsearHorario, serializarHorario } from "./validacion-alta.js";

/* Catálogo de especialidades (GET /directorio-proveedores/especialidades).
   Sale de la tabla especialidades_catalogo de SQLite, sembrada con el
   catálogo del sistema central -- ver app/repositories/especialidades_repo.py.

   Trae ya partido lo que va en tarjeta (las 16 primeras según ordenKPI) y lo
   que va en el combo, más el KPI real de cada una: cuántos proveedores hay
   dentro y fuera de la red. null mientras no se ha pedido. */
let especialidadesKpi = null;

export async function cargarEspecialidadesKpi() {
  if (especialidadesKpi) return especialidadesKpi;
  try {
    especialidadesKpi = await api("/directorio-proveedores/especialidades");
  } catch (err) {
    especialidadesKpi = { total: 0, maximo_tarjetas: 0, tarjetas: [], combo: [] };
  }
  return especialidadesKpi;
}

export function especialidadesKpiCache() {
  return especialidadesKpi || { total: 0, maximo_tarjetas: 0, tarjetas: [], combo: [] };
}

/* Las 38 juntas, en el orden del KPI: es lo que necesita el combo del Alta
   de médico (ahí no se parte en tarjetas y combo). */
export function todasLasEspecialidades() {
  const c = especialidadesKpiCache();
  return [...c.tarjetas, ...c.combo];
}

/* Se vuelve a pedir cuando el padrón cambió (carga de Excel o alta
   aprobada): los conteos del KPI ya no son los mismos. */
export function olvidarEspecialidadesKpi() {
  especialidadesKpi = null;
}

/* Rangos del filtro de precio. No son un dato, son los cortes del filtro:
   se comparan contra el costo de consulta real de cada proveedor. */
export const PRICE_OPTIONS = [
  { label: "Hasta $600", max: 600 }, { label: "Hasta $900", max: 900 },
  { label: "Hasta $1,200", max: 1200 }, { label: "Sin límite", max: 9999 }
];
// Misma llave que el original: las búsquedas recientes se comparten con él
// si alguna vez se abren en el mismo origen.
export const RECENT_KEY = "portalProveedores.recientes";

/* Formulario de alta vacío (el de arranque y al que regresa "Registrar otro
   médico"). El domicilio va desglosado: es el del lugar DONDE DA LA
   CONSULTA, igual que en la carga de Excel. Estado/Municipio arrancan
   vacíos a propósito: ya no son el catálogo simulado de Zona, hay que
   elegirlos del catálogo real (ver cargarEntidadesAltaReal). */
export function formularioVacio() {
  return {
    // La especialidad arranca vacía, igual que Estado/Municipio: sale del
    // catálogo real (ver cargarEspecialidadesKpi), no de una lista fija.
    name: "", specialty: "", cedula: "", rfc: "",
    estado: "", municipio: "",
    calleNumExtInt: "", colonia: "", codigoPostal: "",
    consultorio: "",
    // Horario de atención: bloques { dias, desde, hasta } (ver validacion-alta.js).
    horarioBloques: [bloqueHorarioVacio()],
    // Rango de COSTOS_APROXIMADOS (ver validacion-alta.js).
    costoConsulta: "",
    phone: "", email: "",
  };
}

/* ---------- Entidad/Municipio del Alta de médico ----------
   Mismo catálogo de Entidad que usa Seguimiento/Expedientes (32 entidades),
   pero con su CodEnt real (GET /catalogos/entidades, ver
   app/repositories/catalogos_repo.py) y SIN la opción "Todas" -- aquí
   siempre se está dando de alta a un médico puntual. El municipio sale de
   dbo.sp_GetMun (GET /catalogos/municipios?cod_ent=...), cacheado por
   entidad para no volver a pedirlo si el usuario va y viene. */
let entidadesAlta = null;
// true cuando el último intento de cargar el catálogo falló -- la pantalla lo
// usa para avisar en vez de mostrar un combo vacío sin explicación.
let entidadesAltaFallo = false;
const municipiosPorEntidad = new Map();

export async function cargarEntidadesAltaReal() {
  if (entidadesAlta) return entidadesAlta;
  try {
    entidadesAlta = await api("/catalogos/entidades");
    entidadesAltaFallo = false;
  } catch (err) {
    // NO se cachea el fallo: si se guardara [] aquí, el `if (entidadesAlta)`
    // de arriba lo tomaría como "ya cargado" (un array vacío es truthy) y el
    // combo se quedaría vacío el resto de la sesión, sin reintentar ni
    // avisar. Devolviendo [] sin asignarlo, la próxima llamada vuelve a
    // intentar. El aviso al usuario lo da quien llama (ver
    // entidadesAltaFallaron).
    entidadesAltaFallo = true;
    return [];
  }
  return entidadesAlta;
}

export function entidadesAltaFallaron() {
  return entidadesAltaFallo;
}

export function entidadesAltaCache() {
  return entidadesAlta || [];
}

export async function cargarMunicipiosAltaReal(codEnt) {
  if (!codEnt) return [];
  if (municipiosPorEntidad.has(codEnt)) return municipiosPorEntidad.get(codEnt);
  try {
    const municipios = await api("/catalogos/municipios", { params: { cod_ent: codEnt } });
    municipiosPorEntidad.set(codEnt, municipios);
    return municipios;
  } catch (err) {
    // Igual que con las entidades: NO se cachea el fallo, para que la próxima
    // vez se reintente en vez de quedarse vacío el resto de la sesión.
    return [];
  }
}

export function municipiosAltaCache(codEnt) {
  return municipiosPorEntidad.get(codEnt) || [];
}

/* true cuando ya se pidió la lista de municipios de esa entidad (haya venido
   con datos o vacía). Sirve para distinguir "Cargando…" de "esta entidad no
   tiene municipios", que antes se veían igual y dejaba el combo en
   "Cargando…" para siempre. */
export function municipiosAltaCargados(codEnt) {
  return municipiosPorEntidad.has(codEnt);
}

/* Catálogo real (cargado por Administrador, ver GET /directorio-proveedores)
   -- null mientras no se ha pedido todavía, [] si ya se pidió y vino vacío. */
let catalogoReal = null;

/* Las dos etiquetas de origen del padrón: un proveedor que llegó en el Excel
   oficial tiene convenio con IKE ("Dentro de la red"); uno aprobado en el
   portal, sin ese proceso formal, cuenta como "Fuera de la red" hasta que
   llegue en una carga de Excel (ver mapearProveedor abajo). */
export const ETIQUETA_DENTRO_DE_LA_RED = "Dentro de la red";
export const ETIQUETA_FUERA_DE_LA_RED = "Fuera de la red";

/* Domicilio DONDE DA LA CONSULTA, en el orden que se pidió:
   calle con números, colonia y código postal. */
function domicilioConsulta(row) {
  const cp = row.codigo_postal ? "C.P. " + row.codigo_postal : "";
  return [row.calle_num_ext_int, row.colonia, cp].filter(Boolean).join(", ");
}

function mapearProveedor(row) {
  const costo = leerCosto(row.costo_consulta);
  const esPortal = row.origen === "portal";
  return {
    // La clave la genera el portal (PRV-000001) y es la misma para los dos
    // orígenes: con ella se agenda la cita y no cambia aunque el médico
    // llegue después en la carga de Excel (ver proveedores_repo.py).
    id: String(row.clave ?? ""),
    clave: String(row.clave ?? ""),
    claveSistemaCentral: row.cl_proveedor ?? null,
    folioAlta: row.folio_alta || "",
    name: row.nombre,
    specialty: row.especialidad || "Sin especialidad",
    // A qué especialidad del catálogo quedó amarrado (null si su nombre no
    // empató). Es con esto que se filtra al picarle a una tarjeta: filtrar
    // por el texto haría que la tarjeta dijera "1 dentro de la red" y los
    // resultados salieran vacíos, porque el padrón guarda el nombre como
    // venga en el Excel ("Traumatología") y el catálogo el oficial
    // ("TRAUMATOLOGIA Y ORTOPEDIA").
    clEspecialidad: row.cl_especialidad ?? null,
    estado: row.estado || "",
    municipio: row.municipio || "",
    cedula: row.cedula || "",
    clinic: row.consultorio || "Consultorio no especificado",
    address: domicilioConsulta(row),
    calleNumExtInt: row.calle_num_ext_int || "",
    colonia: row.colonia || "",
    schedule: row.horario || "Horario no especificado",
    // Solo lo que el padrón trae de verdad. Ya no se inventan calificación,
    // distancia ni "disponible hoy": no hay reseñas, ni geolocalización del
    // usuario, ni agenda consultada en este punto.
    // null = costo desconocido: no entra a los filtros "Hasta $..." y va al
    // final al ordenar por precio (antes contaba como $0 y salía el más barato).
    priceNum: costo.maximo,
    price: costo.texto,
    tele: !!row.teleconsulta,
    convenio: row.convenio || "Sin convenio",
    phone: row.telefono || "",
    email: row.email || "",
    codigoPostal: row.codigo_postal || "",
    latitud: row.latitud ?? null,
    longitud: row.longitud ?? null,
    source: esPortal ? ETIQUETA_FUERA_DE_LA_RED : ETIQUETA_DENTRO_DE_LA_RED,
    origen: esPortal ? "portal" : "catalogo",
  };
}

/* Cifras del padrón que ya se cargó, para los KPI de Métricas. Se cuentan
   TODOS los renglones, traigan domicilio o no (las zonas sí dependen del
   domicilio, ver zonasDelPadron). */
export function resumenDelPadron() {
  const lista = catalogoReal || [];
  const especialidades = new Set();
  let dentro = 0;
  let fuera = 0;
  lista.forEach(d => {
    if (d.origen === "portal") fuera += 1;
    else dentro += 1;
    if (d.clEspecialidad) especialidades.add(d.clEspecialidad);
  });
  return {
    total: lista.length,
    dentroDeRed: dentro,
    fueraDeRed: fuera,
    especialidadesConProveedor: especialidades.size,
  };
}

/* ---------- Zonas del padrón ----------
   La pantalla de Zona ofrece los estados y municipios DONDE DE VERDAD HAY
   proveedores, calculados del padrón que ya se cargó. Antes eran seis
   estados fijos en el código con municipios inventados, así que se podía
   elegir una zona en la que nunca hubo nadie.

   Con el portal recién desplegado esto devuelve [] y la pantalla lo dice:
   no hay zonas porque no hay padrón todavía. */
export function zonasDelPadron(clEspecialidad) {
  const porEstado = new Map();
  (catalogoReal || []).forEach(d => {
    if (clEspecialidad && d.clEspecialidad !== clEspecialidad) return;
    const estado = (d.estado || "").trim();
    const municipio = (d.municipio || "").trim();
    if (!estado || !municipio) return;
    if (!porEstado.has(estado)) porEstado.set(estado, new Map());
    const municipios = porEstado.get(estado);
    municipios.set(municipio, (municipios.get(municipio) || 0) + 1);
  });

  return [...porEstado.entries()]
    .map(([name, municipios]) => ({
      name,
      total: [...municipios.values()].reduce((a, b) => a + b, 0),
      municipios: [...municipios.entries()]
        .map(([nombre, total]) => ({ name: nombre, total }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/* Trae el catálogo real una vez (ver pantallas/directorio-proveedores.js,
   se llama al montar la pantalla). Si falla (red, permisos), se deja como
   lista vacía -- la búsqueda/resultados simplemente no encuentran nada en
   vez de tronar. */
export async function cargarCatalogoReal() {
  try {
    const filas = await api("/directorio-proveedores");
    catalogoReal = filas.map(mapearProveedor);
  } catch (err) {
    catalogoReal = [];
  }
  return catalogoReal;
}

/* ---------- Alta de médico (ver pantallas/directorio-proveedores.js) ----------
   La solicitud y su estatus quedan SOLO en este portal (nunca se mandan al
   sistema central). Al aprobarse, el médico entra al padrón con su propia
   clave y queda como "Fuera de la red" hasta que llegue en una carga de Excel:
   ahí el MISMO renglón pasa a "Dentro de la red" conservando su clave, así
   que sus citas no se pierden.

   De la cédula y el RFC solo se valida el formato (ver
   validacion-alta.js); para confirmarlos, Solicitudes lleva al sitio del
   SAT y de la SEP. */
export async function cargarSolicitudesReales() {
  try {
    const filas = await api("/solicitudes-alta-medico");
    return filas.map(f => ({
      folio: f.folio, name: f.nombre, specialty: f.especialidad,
      zone: [f.municipio, f.estado].filter(Boolean).join(", "),
      cedula: f.cedula || "", rfc: f.rfc || "", status: f.estatus,
      consultorio: f.consultorio || "", horario: f.horario || "", costo: f.costo_consulta || "",
      claveProveedor: f.clave_proveedor || "",
      // Cómo se ve el RFC (tipo de persona, dígito verificador) y qué
      // documentos opcionales se subieron (solo nombre y fecha).
      rfcRevision: f.rfc_revision || { tipo: null, formato_valido: false, digito_correcto: false },
      documentos: f.documentos || {},
      rfcSolicito: f.rfc_solicito || "",
      // Los datos crudos, con los que el botón "Editar" rellena el
      // formulario (el resto de campos de arriba ya vienen formateados
      // para la tabla, con "—" y zonas concatenadas).
      form: {
        name: f.nombre || "", specialty: f.especialidad || "",
        cedula: f.cedula || "", rfc: f.rfc || "",
        estado: f.estado || "", municipio: f.municipio || "",
        calleNumExtInt: f.calle_num_ext_int || "", colonia: f.colonia || "",
        codigoPostal: f.codigo_postal || "",
        consultorio: f.consultorio || "",
        // Una solicitud vieja (sin horario o con otro formato) vuelve a capturarlo.
        horarioBloques: parsearHorario(f.horario).length ? parsearHorario(f.horario) : [bloqueHorarioVacio()],
        costoConsulta: f.costo_consulta || "",
        // Solo dígitos: las solicitudes viejas pudieron guardar el teléfono con espacios.
        phone: (f.telefono || "").replace(/\D/g, ""), email: f.email || "",
      },
    }));
  } catch (err) {
    return [];
  }
}

/* Corrige una solicitud que sigue "En revisión" (solo Administrador, ver
   app/routers/solicitudes_alta_medico.py). */
export function editarSolicitudAlta(folio, form) {
  const ubicacion = nombresDeUbicacion(form);
  return api("/solicitudes-alta-medico/" + encodeURIComponent(folio), {
    method: "PUT",
    body: {
      nombre: form.name, especialidad: form.specialty, cedula: form.cedula, rfc: form.rfc,
      estado: ubicacion.estado, municipio: ubicacion.municipio,
      calle_num_ext_int: form.calleNumExtInt || null,
      colonia: form.colonia || null,
      codigo_postal: form.codigoPostal || null,
      consultorio: form.consultorio || null,
      horario: serializarHorario(form.horarioBloques) || null,
      costo_consulta: form.costoConsulta || null,
      telefono: form.phone || null, email: form.email || null,
    },
  });
}

/* form.estado/form.municipio guardan el CodEnt/CodMD (para encadenar los
   combos) -- lo que se manda a guardar es el NOMBRE, igual que el resto del
   padrón (carga de Excel, búsqueda libre por texto). */
function nombresDeUbicacion(form) {
  const entidad = entidadesAltaCache().find(e => String(e.clave) === String(form.estado));
  const municipio = municipiosAltaCache(form.estado).find(m => String(m.clave) === String(form.municipio));
  return {
    estado: entidad ? entidad.descripcion : (form.estado || null),
    municipio: municipio ? municipio.descripcion : (form.municipio || null),
  };
}

/* Lo contrario: de los NOMBRES guardados en una solicitud a las claves que
   usan los combos (para editarla). Carga los catálogos que haga falta. Lo que
   no se encuentre regresa vacío, para que se vuelva a elegir. */
const comoTexto = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toUpperCase();

export async function clavesDeUbicacion(nombreEstado, nombreMunicipio) {
  const entidades = await cargarEntidadesAltaReal();
  const entidad = entidades.find(e => comoTexto(e.descripcion) === comoTexto(nombreEstado));
  if (!entidad) return { estado: "", municipio: "" };
  const municipios = await cargarMunicipiosAltaReal(entidad.clave);
  const municipio = municipios.find(m => comoTexto(m.descripcion) === comoTexto(nombreMunicipio));
  return { estado: String(entidad.clave), municipio: municipio ? String(municipio.clave) : "" };
}

export function enviarSolicitudAlta(form) {
  const ubicacion = nombresDeUbicacion(form);
  return api("/solicitudes-alta-medico", {
    method: "POST",
    body: {
      nombre: form.name, especialidad: form.specialty, cedula: form.cedula, rfc: form.rfc,
      estado: ubicacion.estado,
      municipio: ubicacion.municipio,
      calle_num_ext_int: form.calleNumExtInt || null,
      colonia: form.colonia || null,
      codigo_postal: form.codigoPostal || null,
      consultorio: form.consultorio || null,
      horario: serializarHorario(form.horarioBloques) || null,
      costo_consulta: form.costoConsulta || null,
      telefono: form.phone || null, email: form.email || null,
    },
  });
}

/* Documentos opcionales de una solicitud (constancia fiscal y cédula). Los
   ve y los cambia solo el Administrador o quien capturó la solicitud. */
const rutaDocumento = (folio, tipo) =>
  "/solicitudes-alta-medico/" + encodeURIComponent(folio) + "/documentos/" + encodeURIComponent(tipo);

export function subirDocumentoSolicitud(folio, tipo, archivo) {
  const formData = new FormData();
  formData.append("archivo", archivo);
  return api(rutaDocumento(folio, tipo), { method: "POST", formData });
}

export function quitarDocumentoSolicitud(folio, tipo) {
  return api(rutaDocumento(folio, tipo), { method: "DELETE" });
}

export function descargarDocumentoSolicitud(folio, tipo) {
  return apiArchivo(rutaDocumento(folio, tipo), "No se pudo abrir el documento.");
}

export function actualizarEstatusSolicitud(folio, estatus) {
  return api("/solicitudes-alta-medico/" + encodeURIComponent(folio) + "/estatus", {
    method: "POST",
    body: { estatus },
  });
}

/* Normaliza para comparar texto escrito por una persona contra el padrón.
   Quita los acentos a propósito: el padrón guarda los municipios como los
   entrega el sistema central ("MERIDA", "YUCATAN"), pero quien busca escribe
   "Mérida". Sin esto, la búsqueda con acento no encontraba nada. */
function normalizar(texto) {
  return (texto || "")
    .toString()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

/* Valores únicos de un campo del catálogo real, para las sugerencias del
   buscador (ver calcularSugerencias en vistas.js). */
export function valoresUnicosCatalogo(campo) {
  const vistos = new Set();
  const out = [];
  (catalogoReal || []).forEach(d => {
    const valor = (d[campo] || "").toString().trim();
    const clave = valor.toLowerCase();
    if (valor && !vistos.has(clave)) { vistos.add(clave); out.push(valor); }
  });
  return out;
}

/* Lista "cruda" según el estado actual: por búsqueda libre o por zona
   elegida (pantalla "Zona") -- ambas leen del catálogo real cargado por
   Administrador, ver cargarCatalogoReal(). */
export function raw(s) {
  const catalogo = catalogoReal || [];
  if (s.searchTerm) {
    const t = normalizar(s.searchTerm);
    const list = catalogo.filter(d =>
      normalizar(d.name).includes(t) || normalizar(d.specialty).includes(t) ||
      normalizar(d.estado).includes(t) || normalizar(d.municipio).includes(t)
    );
    return {
      list,
      label: list.length ? `Resultados para "${s.searchTerm}"` : "Sin resultados para «" + s.searchTerm + "»",
      sub: list.length ? list.length + " especialista(s) encontrados" : "No encontramos coincidencias en el catálogo cargado",
    };
  }
  if (s.specialty && s.municipio) {
    // Por cl_especialidad cuando se llegó desde una tarjeta/combo del
    // catálogo, y por texto solo como respaldo (p. ej. una especialidad
    // vieja que ya no está en el catálogo): así el conteo de la tarjeta y
    // los resultados siempre dicen lo mismo.
    const mismaEspecialidad = s.specialtyId
      ? (d => d.clEspecialidad === s.specialtyId)
      : (d => normalizar(d.specialty) === normalizar(s.specialty));
    const list = catalogo.filter(d => mismaEspecialidad(d) && normalizar(d.municipio) === normalizar(s.municipio));
    return { list, label: s.specialty + " en " + s.municipio, sub: s.municipio + ", " + s.estado };
  }
  return { list: [], label: "", sub: "" };
}

/* Lista ya filtrada y ordenada (lo que se ve en Resultados y en el mapa).

   Solo quedan los filtros y los órdenes que se pueden resolver con datos
   reales del padrón. Se quitaron "Disponible hoy" (el padrón no dice la
   disponibilidad; eso lo sabe la agenda, que se consulta al abrir la ficha)
   y "Solo directorio verificado" (marcaba los importados de Google Places,
   que nunca existieron). Ordenar por calificación o por cercanía tampoco
   tiene con qué: no hay reseñas ni geolocalización. */
export function visible(s) {
  const f = s.filters;
  const sinLimite = f.maxPrice >= 9999;
  const list = raw(s).list.filter(d =>
    // Con "Sin límite" entran todos; con un tope, solo los que tienen costo
    // conocido y dentro de él (un costo desconocido no se puede prometer).
    (sinLimite || (d.priceNum !== null && d.priceNum <= f.maxPrice)) &&
    (!f.tele || d.tele) &&
    (!f.seguro || d.convenio !== "Sin convenio")
  );
  const sorters = {
    nombre: (a, b) => a.name.localeCompare(b.name),
    // Los de costo desconocido van al final.
    precio: (a, b) => (a.priceNum ?? Infinity) - (b.priceNum ?? Infinity) || a.name.localeCompare(b.name),
  };
  return list.slice().sort(sorters[f.orden] || sorters.nombre);
}

/* ---------- Búsqueda fuera de la red (Google Maps) ----------
   Cuando no hay nadie de la red en esa zona, se ofrecen establecimientos de
   Google Maps (Places API) como CANDIDATOS a contratar -- no son
   proveedores del portal: no tienen clave PRV-, no se les puede agendar y
   no se guardan en ningún lado (cada búsqueda va en vivo a Google, ver
   app/services/google_maps_service.py). Para incorporar a uno hay que
   darlo de alta, con su validación de cédula y la aprobación de un
   Administrador. Responde 503 mientras no haya GOOGLE_MAPS_API_KEY en el
   .env del servidor. */
export async function buscarFueraDeRedGoogle({ codEnt, codMun, especialidad }) {
  return api("/directorio-proveedores/fuera-de-red-google-maps", {
    params: { cod_ent: codEnt, cod_mun: codMun || undefined, especialidad },
  });
}

/* Llave del navegador para pintar el mapa de Google (Maps JavaScript API).
   Es una llave DISTINTA de la del servidor, restringida por dominio -- ver
   GET /directorio-proveedores/configuracion-mapa. Regresa { llave: null }
   mientras no esté configurada. */
export async function configuracionMapa() {
  return api("/directorio-proveedores/configuracion-mapa");
}

/* ---------- Citas ----------
   La disponibilidad la decide el servidor: es el único que sabe qué horarios
   ya están apartados. Antes se inventaba con un hash, así que dos personas
   veían el mismo hueco libre y la cita no quedaba registrada en ningún lado. */
export async function cargarAgenda(claveProveedor, desde) {
  try {
    // Sin `desde`: los próximos 7 días. Con `desde` (YYYY-MM-DD): solo ese día,
    // para los horarios sugeridos de una fecha libre.
    const opciones = desde ? { params: { desde, dias: 1 } } : undefined;
    return await api("/directorio-proveedores/" + encodeURIComponent(claveProveedor) + "/agenda", opciones);
  } catch (err) {
    return [];
  }
}

/* Toda cita es para un expediente: el servidor toma el paciente de ahí, liga
   la cita y regresa el texto para Observaciones. */
export function agendarCita({ claveProveedor, fecha, hora, clExpediente }) {
  return api("/directorio-proveedores/citas", {
    method: "POST",
    body: { clave_proveedor: claveProveedor, fecha, hora, cl_expediente: clExpediente },
  });
}

/* Los expedientes a los que se les puede agendar cita ahora (en espera y sin
   cita): la lista del paso "¿Para qué expediente?". Mismo formato que la
   lista de Expedientes, así se puede abrir Seguimiento con el mismo registro. */
export function cargarExpedientesParaCita() {
  return api("/directorio-proveedores/expedientes-para-cita");
}

export async function cargarCitas(claveProveedor) {
  try {
    return await api("/directorio-proveedores/citas", {
      params: claveProveedor ? { clave_proveedor: claveProveedor } : undefined,
    });
  } catch (err) {
    return [];
  }
}

/* ---------- Coordinar cita desde un expediente ----------
   A dónde llevar al Proveedor en el directorio según lo que SÍ trae el
   expediente: se baja hasta donde alcancen los datos y ahí se detiene, para
   que lo que falte lo elija él.

     sin especialidad reconocida  -> inicio (tarjetas de especialidad)
     especialidad                 -> zona de esa especialidad (elige estado)
     + estado                     -> zona con ese estado (elige municipio)
     + municipio                  -> lista de médicos

   Si el expediente trae el dato pero en el padrón no hay nadie ahí, se queda
   un nivel antes, con la nota que lo explica y el acceso a buscar fuera de la
   red. La especialidad se compara por nombre completo, sin acentos ni
   mayúsculas: viene del mismo catálogo del sistema central que usa el
   directorio, así que cuando existe, coincide. */
const sinAcentos = (t) => normalizar(t).toUpperCase();

export function buscarEspecialidadPorNombre(nombre) {
  const buscado = sinAcentos(nombre);
  if (!buscado) return null;
  return todasLasEspecialidades().find(x => sinAcentos(x.descripcion) === buscado) || null;
}

export function resolverBusquedaDeExpediente({ especialidad, entidad, municipio }) {
  const base = { screen: "home", especialidad: null, estado: null, municipio: null, nota: "", fuera: false };

  const esp = buscarEspecialidadPorNombre(especialidad);
  if (!esp) {
    return {
      ...base,
      nota: (especialidad || "").trim()
        ? `La especialidad del expediente («${especialidad}») no está en el catálogo del directorio: elige la especialidad.`
        : "El expediente no trae especialidad: elige la especialidad.",
    };
  }
  const conEspecialidad = { ...base, screen: "zone", especialidad: esp };

  if (!(entidad || "").trim()) {
    return { ...conEspecialidad, nota: "El expediente no trae estado: elige el estado." };
  }
  const estado = zonasDelPadron(esp.cl_especialidad)
    .find(z => normalizarEntidad(z.name) === normalizarEntidad(entidad));
  if (!estado) {
    return {
      ...conEspecialidad, fuera: true,
      nota: `No hay médicos de ${esp.descripcion} en ${entidad}. Elige otra zona, busca fuera de la red o da de alta a un médico.`,
    };
  }
  const conEstado = { ...conEspecialidad, estado: estado.name };

  if (!(municipio || "").trim()) {
    return { ...conEstado, nota: "El expediente no trae municipio: elige el municipio." };
  }
  const mun = estado.municipios.find(m => sinAcentos(m.name) === sinAcentos(municipio));
  if (!mun) {
    return {
      ...conEstado, fuera: true,
      nota: `No hay médicos de ${esp.descripcion} en ${municipio}. Elige otro municipio o busca fuera de la red.`,
    };
  }
  return { ...conEstado, screen: "results", municipio: mun.name };
}
