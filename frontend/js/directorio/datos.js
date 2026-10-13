/* Directorio de Proveedores (maqueta): datos simulados y generadores.
   Portados TAL CUAL del prototipo original "Portal de búsqueda de
   proveedores": misma lista de especialidades, estados, municipios y
   nombres, y la misma matemática (hash FNV-1a) para generar médicos,
   precios, calificaciones y horarios. Así, para la misma zona salen
   exactamente los mismos médicos y en el mismo orden que en el original.
   No hay conexión con el backend: todo vive en el navegador. */

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

export const CALLES = ["Av. Vallarta", "Blvd. Constitución", "Calle Morelos", "Av. Reforma", "Calzada del Valle", "Paseo Montejo", "Av. Juárez", "Calle 60 Norte"];
export const COLONIAS = ["Col. Americana", "Centro", "Col. del Valle", "Zona Río", "Col. Itzimná", "Lomas Verdes", "Col. Roma Norte"];
export const HORARIOS = ["Lun–Vie 09:00–14:00", "Lun–Sáb 10:00–18:00", "Mar–Sáb 08:00–13:00", "Lun–Vie 16:00–20:00", "Lun–Jue 09:00–17:00"];
export const CONVENIOS = ["Convenio GNP", "Convenio AXA", "Convenio MetLife", "Sin convenio"];
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

/* Médico número i de una zona (especialidad + estado + municipio). Cada 4o
   (i % 4 === 3) viene "de Google Places". */
export function doctorAt(specialty, estado, municipio, i) {
  const seed = specialty + estado + municipio + i;
  const fromPlaces = i % 4 === 3;
  const priceNum = num(seed, "p", 5, 14) * 100;
  const ratingNum = 4 + num(seed, "r", 0, 9) / 10;
  const distNum = num(seed, "d", 4, 92) / 10;
  return {
    id: seed, name: pick(NOMBRES, seed, "n"), specialty, estado, municipio,
    cedula: String(num(seed, "c", 1000000, 99999999)).slice(0, 8),
    clinic: fromPlaces ? "Clínica " + pick(["Santa Fe", "Del Bosque", "Angelis", "Nova Salud", "San Rafael"], seed, "cl") : "Consultorio " + pick(["101", "204", "3B", "512", "8"], seed, "cn"),
    address: pick(CALLES, seed, "ca") + " " + num(seed, "no", 120, 2400) + ", " + pick(COLONIAS, seed, "co"),
    schedule: pick(HORARIOS, seed, "h"),
    ratingNum, rating: ratingNum.toFixed(1) + " ★",
    priceNum, price: "$" + priceNum + " consulta",
    distNum, distance: distNum.toFixed(1) + " km",
    hoy: hash(seed + "hoy") % 2 === 0,
    tele: hash(seed + "tel") % 3 === 0,
    convenio: pick(CONVENIOS, seed, "cv"),
    phone: num(seed, "t", 30, 99) + " " + num(seed, "t2", 1000, 9999) + " " + num(seed, "t3", 1000, 9999),
    source: fromPlaces ? "Google Places" : "Directorio verificado",
    fromPlaces
  };
}

/* Lista de una zona. Los de Google Places solo aparecen ya sincronizado. */
export function buildList(specialty, estado, municipio, placesSynced) {
  const total = num(specialty + estado + municipio, "len", 5, 9);
  const out = [];
  for (let i = 0; i < total; i++) {
    const d = doctorAt(specialty, estado, municipio, i);
    if (d.fromPlaces && !placesSynced) continue;
    out.push(d);
  }
  return out;
}

/* Búsqueda libre: reconoce municipio/estado y/o especialidad en el texto. */
export function searchResults(term, placesSynced) {
  const t = term.trim().toLowerCase();
  if (!t) return { list: [], label: "Sin término de búsqueda", sub: "" };
  let estado = null, municipio = null, specialty = null;
  ESTADOS.forEach(e => {
    if (e.name.toLowerCase().includes(t)) { estado = e.name; municipio = e.municipios[0]; }
    e.municipios.forEach(m => { if (m.toLowerCase().includes(t)) { estado = e.name; municipio = m; } });
  });
  SPECIALTIES.forEach(s => { if (s.toLowerCase().includes(t)) specialty = s; });
  if (municipio && specialty) return { list: buildList(specialty, estado, municipio, placesSynced), label: specialty + " en " + municipio, sub: municipio + ", " + estado };
  if (municipio) {
    const list = [];
    SPECIALTIES.slice(0, 5).forEach(s => buildList(s, estado, municipio, placesSynced).slice(0, 2).forEach(d => list.push(d)));
    return { list, label: "Especialistas en " + municipio, sub: municipio + ", " + estado + " · todas las especialidades" };
  }
  if (specialty) {
    const list = [];
    ESTADOS.slice(0, 4).forEach(e => buildList(specialty, e.name, e.municipios[0], placesSynced).slice(0, 2).forEach(d => list.push(d)));
    return { list, label: specialty, sub: "Resultados en las zonas con mayor cobertura" };
  }
  return { list: [], label: "Sin resultados para «" + term + "»", sub: "No encontramos coincidencias" };
}

/* Lista "cruda" según el estado actual: por búsqueda o por zona elegida. */
export function raw(s) {
  if (s.searchTerm) return searchResults(s.searchTerm, s.placesSynced);
  if (s.specialty && s.municipio) return { list: buildList(s.specialty, s.estado, s.municipio, s.placesSynced), label: s.specialty + " en " + s.municipio, sub: s.municipio + ", " + s.estado };
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
