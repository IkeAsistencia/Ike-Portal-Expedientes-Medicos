/* Directorio de Proveedores (maqueta): datos simulados y generadores.
   Portados TAL CUAL del prototipo original "Portal de búsqueda de
   proveedores": misma lista de especialidades, estados, municipios y
   nombres, y la misma matemática (hash FNV-1a) para generar médicos,
   precios, calificaciones y horarios. Así, para la misma zona salen
   exactamente los mismos médicos y en el mismo orden que en el original.

   ÚNICA EXCEPCIÓN: la búsqueda y la lista de resultados (ver raw()/visible()
   más abajo) sí están conectadas al catálogo real que carga Administrador
   (ver pantallas/directorio-proveedores-carga.js) -- cargarCatalogoReal()
   trae ese catálogo una vez al entrar a la pantalla. El resto (reservar
   cita, comparador, panel de Métricas/Solicitudes, alta de médico) se
   queda igual que antes, con datos simulados: no hay horarios/calificaciones
   reales ni validación real de cédula todavía. */
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

export const SLOTS = ["09:00", "10:30", "12:00", "13:30", "16:00", "17:30", "19:00"];
export const DOW = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
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

export const SEED_REQUESTS = [
  { folio: "ALT-40218", name: "Dr. Óscar Palomino Reyes", specialty: "Traumatología", zone: "Monterrey, Nuevo León", cedula: "7412985", rfc: "PARO790612K41", status: "En revisión" },
  { folio: "ALT-40219", name: "Dra. Itzel Guerra Domínguez", specialty: "Pediatría", zone: "Mérida, Yucatán", cedula: "10238471", rfc: "GUDI880903M12", status: "Validada" },
  { folio: "ALT-40221", name: "Dr. Fabián Cortés Núñez", specialty: "Dermatología", zone: "Zapopan, Jalisco", cedula: "553219", rfc: "CONF830127P08", status: "Cédula no localizada" },
  { folio: "ALT-40224", name: "Dra. Sandra Uribe Lozano", specialty: "Endocrinología", zone: "Puebla, Puebla", cedula: "9081726", rfc: "URLS910418D55", status: "En revisión" }
];

/* Formulario de alta vacío (el mismo con el que arranca el original y al
   que regresa "Registrar otro médico"). */
export function formularioVacio() {
  return { name: "", specialty: SPECIALTIES[0], cedula: "", rfc: "", estado: ESTADOS[0].name, municipio: ESTADOS[0].municipios[0], address: "", phone: "", email: "" };
}

/* Catálogo real (cargado por Administrador, ver GET /directorio-proveedores)
   -- null mientras no se ha pedido todavía, [] si ya se pidió y vino vacío. */
let catalogoReal = null;

function mapearProveedor(row) {
  const costo = parseFloat(row.costo_consulta);
  return {
    id: String(row.cl_proveedor),
    name: row.nombre,
    specialty: row.especialidad || "Sin especialidad",
    estado: row.estado || "",
    municipio: row.municipio || "",
    cedula: row.cedula || "",
    clinic: row.consultorio || "Consultorio no especificado",
    address: row.direccion || "",
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
    source: "Catálogo cargado",
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

/* Horarios libres de un médico en el día dayIndex (0 = hoy). */
export function slotsFor(doctor, dayIndex) {
  if (!doctor) return [];
  return SLOTS.filter(sl => hash(doctor.id + dayIndex + sl) % 3 !== 0);
}
