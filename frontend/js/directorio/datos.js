/* Directorio de Proveedores: datos de la pantalla.

   YA ESTÁ CONECTADO AL BACKEND:
     - Búsqueda y resultados: leen el padrón real (GET /directorio-proveedores),
       con los dos orígenes juntos -- "Dentro de la red" (llegó en la carga de
       Excel) y "Fuera de la red" (alta hecha en el portal).
     - Alta de médico y sus solicitudes: se guardan de verdad; al aprobarse,
       el médico entra al padrón con su propia clave (PRV-000001).
     - Citas: se agendan contra esa clave y quedan registradas; los horarios
       libres los decide el servidor (GET /directorio-proveedores/{clave}/agenda),
       no un hash del navegador como antes.

   SIGUE SIMULADO: la validación de la cédula profesional contra el RNP y el
   panel de Métricas (no hay reseñas ni geolocalización todavía). Las listas
   de especialidades/estados/municipios de aquí abajo son las del catálogo
   base para los combos del alta y de la zona. */
import { api } from "../core/api.js";

export const SPECIALTIES = [
  "Medicina General", "Psicología", "Nutrición", "Cardiología", "Ginecología", "Pediatría",
  "Dermatología", "Traumatología", "Oftalmología", "Odontología", "Neurología", "Endocrinología"
];

export const ESTADOS = [
  { name: "Jalisco", municipios: ["Guadalajara", "Zapopan", "San Pedro Tlaquepaque", "Tonalá", "Puerto Vallarta"] },
  { name: "Ciudad de México", municipios: ["Benito Juárez", "Cuauhtémoc", "Coyoacán", "Miguel Hidalgo", "Álvaro Obregón"] },
  { name: "Nuevo León", municipios: ["Monterrey", "San Pedro Garza García", "Guadalupe", "Apodaca"] },
  { name: "Yucatán", municipios: ["Mérida", "Progreso", "Valladolid"] },
  { name: "Puebla", municipios: ["Puebla", "San Andrés Cholula", "Atlixco"] },
  { name: "Querétaro", municipios: ["Querétaro", "El Marqués", "Corregidora"] }
];

export const NOMBRES = [
  "Dra. Laura Méndez Ruiz", "Dr. Andrés Salcedo Vega", "Dra. Paulina Rentería Cruz", "Dr. Emilio Cárdenas Lara",
  "Dra. Mariana Ochoa Beltrán", "Dr. Rodrigo Ibarra Solís", "Dra. Fernanda Zamora Ríos", "Dr. Héctor Peralta Muñoz",
  "Dra. Claudia Barrios Nava", "Dr. Sergio Loera Fuentes", "Dra. Ana Sofía Treviño Gil", "Dr. Ignacio Robles Pardo",
  "Dra. Verónica Aguilar Sáenz", "Dr. Julián Espinoza Mora", "Dra. Rebeca Villanueva Ponce", "Dr. Marco Delgado Ávila"
];

export const PRICE_OPTIONS = [
  { label: "Hasta $600", max: 600 }, { label: "Hasta $900", max: 900 },
  { label: "Hasta $1,200", max: 1200 }, { label: "Sin límite", max: 9999 }
];
// Misma llave que el original: las búsquedas recientes se comparten con él
// si alguna vez se abren en el mismo origen.
export const RECENT_KEY = "portalProveedores.recientes";

// Opciones fijas del editor del prototipo original (sus "props"), con sus
// valores por defecto: Google Places sí sincroniza, cuadrícula compacta y
// conteo visible en las tarjetas de especialidad.
export const PROPS = { placesSync: true, gridDensity: "compacta", mostrarConteo: true };

/* Hash FNV-1a de 32 bits: la base de todos los datos "aleatorios" (siempre
   da lo mismo para la misma semilla). */
export function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < String(str).length; i++) { h ^= String(str).charCodeAt(i); h = Math.imul(h, 16777619); }
  return Math.abs(h);
}
export const pick = (arr, seed, salt) => arr[hash(seed + "|" + salt) % arr.length];
export const num = (seed, salt, min, max) => min + (hash(seed + "#" + salt) % (max - min + 1));

/* Formulario de alta vacío (el de arranque y al que regresa "Registrar otro
   médico"). El domicilio va desglosado: es el del lugar DONDE DA LA
   CONSULTA, igual que en la carga de Excel. Estado/Municipio arrancan
   vacíos a propósito: ya no son el catálogo simulado de Zona, hay que
   elegirlos del catálogo real (ver cargarEntidadesAltaReal). */
export function formularioVacio() {
  return {
    name: "", specialty: SPECIALTIES[0], cedula: "", rfc: "",
    estado: "", municipio: "",
    calleNumExtInt: "", colonia: "", codigoPostal: "",
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
const municipiosPorEntidad = new Map();

export async function cargarEntidadesAltaReal() {
  if (entidadesAlta) return entidadesAlta;
  try {
    entidadesAlta = await api("/catalogos/entidades");
  } catch (err) {
    entidadesAlta = [];
  }
  return entidadesAlta;
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
    return [];
  }
}

export function municipiosAltaCache(codEnt) {
  return municipiosPorEntidad.get(codEnt) || [];
}

/* Catálogo real (cargado por Administrador, ver GET /directorio-proveedores)
   -- null mientras no se ha pedido todavía, [] si ya se pidió y vino vacío. */
let catalogoReal = null;

/* Las dos etiquetas del semáforo de origen: un proveedor que llegó en la
   carga ya está contratado ("Dentro de la red"); uno dado de alta en el
   portal todavía no ("Fuera de la red"). */
export const ETIQUETA_DENTRO_DE_LA_RED = "Dentro de la red";
export const ETIQUETA_FUERA_DE_LA_RED = "Fuera de la red";

/* Domicilio DONDE DA LA CONSULTA, en el orden que se pidió:
   calle con números, colonia y código postal. */
function domicilioConsulta(row) {
  const cp = row.codigo_postal ? "C.P. " + row.codigo_postal : "";
  return [row.calle_num_ext_int, row.colonia, cp].filter(Boolean).join(", ");
}

function mapearProveedor(row) {
  const costo = parseFloat(row.costo_consulta);
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
    estado: row.estado || "",
    municipio: row.municipio || "",
    cedula: row.cedula || "",
    clinic: row.consultorio || "Consultorio no especificado",
    address: domicilioConsulta(row),
    calleNumExtInt: row.calle_num_ext_int || "",
    colonia: row.colonia || "",
    schedule: row.horario || "Horario no especificado",
    // Sin calificación ni distancia real todavía (no hay reseñas ni
    // geolocalización) -- valores neutros para que ordenar/filtrar no truene.
    ratingNum: 0, rating: "Sin calificación",
    priceNum: Number.isFinite(costo) ? costo : 0,
    price: row.costo_consulta ? "$" + row.costo_consulta + " consulta" : "Costo no especificado",
    distNum: 0, distance: "—",
    hoy: true,
    tele: !!row.teleconsulta,
    convenio: row.convenio || "Sin convenio",
    phone: row.telefono || "",
    email: row.email || "",
    codigoPostal: row.codigo_postal || "",
    latitud: row.latitud ?? null,
    longitud: row.longitud ?? null,
    source: esPortal ? ETIQUETA_FUERA_DE_LA_RED : ETIQUETA_DENTRO_DE_LA_RED,
    origen: esPortal ? "portal" : "catalogo",
    fromPlaces: false,
  };
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
   clave y queda "Fuera de la red" hasta que llegue en una carga de Excel:
   ahí el MISMO renglón pasa a "Dentro de la red" conservando su clave, así
   que sus citas no se pierden.

   Lo único que sigue simulado aquí es la validación de la cédula contra el
   Registro Nacional de Profesionistas. */
export async function cargarSolicitudesReales() {
  try {
    const filas = await api("/solicitudes-alta-medico");
    return filas.map(f => ({
      folio: f.folio, name: f.nombre, specialty: f.especialidad,
      zone: [f.municipio, f.estado].filter(Boolean).join(", "),
      cedula: f.cedula, rfc: f.rfc || "—", status: f.estatus,
      claveProveedor: f.clave_proveedor || "",
      // Los datos crudos, con los que el botón "Editar" rellena el
      // formulario (el resto de campos de arriba ya vienen formateados
      // para la tabla, con "—" y zonas concatenadas).
      form: {
        name: f.nombre || "", specialty: f.especialidad || "",
        cedula: f.cedula || "", rfc: f.rfc || "",
        estado: f.estado || "", municipio: f.municipio || "",
        calleNumExtInt: f.calle_num_ext_int || "", colonia: f.colonia || "",
        codigoPostal: f.codigo_postal || "",
        phone: f.telefono || "", email: f.email || "",
      },
    }));
  } catch (err) {
    return [];
  }
}

/* Corrige una solicitud que sigue "En revisión" (solo Administrador, ver
   app/routers/solicitudes_alta_medico.py). */
export function editarSolicitudAlta(folio, form) {
  return api("/solicitudes-alta-medico/" + encodeURIComponent(folio), {
    method: "PUT",
    body: {
      nombre: form.name, especialidad: form.specialty, cedula: form.cedula, rfc: form.rfc || null,
      estado: form.estado || null, municipio: form.municipio || null,
      calle_num_ext_int: form.calleNumExtInt || null,
      colonia: form.colonia || null,
      codigo_postal: form.codigoPostal || null,
      telefono: form.phone || null, email: form.email || null,
    },
  });
}

export function enviarSolicitudAlta(form) {
  // form.estado/form.municipio guardan el CodEnt/CodMD (para encadenar el
  // combo) -- lo que se manda a guardar es el NOMBRE, igual que el resto
  // del padrón (carga de Excel, búsqueda libre por texto).
  const entidad = entidadesAltaCache().find(e => e.clave === form.estado);
  const municipio = municipiosAltaCache(form.estado).find(m => m.clave === form.municipio);
  return api("/solicitudes-alta-medico", {
    method: "POST",
    body: {
      nombre: form.name, especialidad: form.specialty, cedula: form.cedula, rfc: form.rfc || null,
      estado: entidad ? entidad.descripcion : (form.estado || null),
      municipio: municipio ? municipio.descripcion : (form.municipio || null),
      calle_num_ext_int: form.calleNumExtInt || null,
      colonia: form.colonia || null,
      codigo_postal: form.codigoPostal || null,
      telefono: form.phone || null, email: form.email || null,
    },
  });
}

export function actualizarEstatusSolicitud(folio, estatus) {
  return api("/solicitudes-alta-medico/" + encodeURIComponent(folio) + "/estatus", {
    method: "POST",
    body: { estatus },
  });
}

function normalizar(texto) {
  return (texto || "").toString().trim().toLowerCase();
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
    const list = catalogo.filter(d => normalizar(d.specialty) === normalizar(s.specialty) && normalizar(d.municipio) === normalizar(s.municipio));
    return { list, label: s.specialty + " en " + s.municipio, sub: s.municipio + ", " + s.estado };
  }
  return { list: [], label: "", sub: "" };
}

/* Lista ya filtrada y ordenada (lo que se ve en Resultados y en el mapa). */
export function visible(s) {
  const f = s.filters;
  const list = raw(s).list.filter(d =>
    d.priceNum <= f.maxPrice &&
    (!f.hoy || d.hoy) && (!f.tele || d.tele) &&
    (!f.seguro || d.convenio !== "Sin convenio") &&
    (!f.soloVerificados || !d.fromPlaces)
  );
  const sorters = {
    rating: (a, b) => b.ratingNum - a.ratingNum,
    precio: (a, b) => a.priceNum - b.priceNum,
    cercania: (a, b) => a.distNum - b.distNum
  };
  return list.slice().sort(sorters[f.orden]);
}

/* ---------- Citas ----------
   La disponibilidad la decide el servidor: es el único que sabe qué horarios
   ya están apartados. Antes se inventaba con un hash, así que dos personas
   veían el mismo hueco libre y la cita no quedaba registrada en ningún lado. */
export async function cargarAgenda(claveProveedor) {
  try {
    return await api("/directorio-proveedores/" + encodeURIComponent(claveProveedor) + "/agenda");
  } catch (err) {
    return [];
  }
}

export function agendarCita({ claveProveedor, fecha, hora, paciente }) {
  return api("/directorio-proveedores/citas", {
    method: "POST",
    body: { clave_proveedor: claveProveedor, fecha, hora, paciente: paciente || null },
  });
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
