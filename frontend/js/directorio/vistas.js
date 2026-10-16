/* Directorio de Proveedores (maqueta): cálculo de lo que se pinta y
   plantillas HTML de cada sub-pantalla.

   calcular(estado) es el equivalente de renderVals() del prototipo
   original: a partir del estado arma todos los textos y listas (mismas
   fórmulas, mismos textos). Las plantillas solo acomodan esos valores con
   el diseño del portal (tarjetas, botones, tablas, badges). Todo texto
   pasa por escapeHtml; los clics se resuelven por delegación con
   data-accion (ver pantallas/directorio-proveedores.js). */
import { escapeHtml as e } from "../core/formato.js";
import { ICONOS } from "../componentes/iconos.js";
import {
  SPECIALTIES, ESTADOS, DOW, PRICE_OPTIONS, PROPS,
  num, pick, raw, visible, slotsFor, valoresUnicosCatalogo,
} from "./datos.js";

const svg = (contenido) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${contenido}</svg>`;

// Íconos de las KPIs de Métricas (trazo 24x24, como los del portal).
const ICONO_KPI = {
  personas: svg(`<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>`),
  ubicacion: ICONOS.ubicacion,
  expediente: ICONOS.expediente,
  nube: svg(`<polyline points="8 17 12 21 16 17"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29"/>`),
};

/* ---------- Sugerencias del buscador (solo en Inicio, desde 2 letras) ----------
   Salen del catálogo real cargado por Administrador (ver cargarCatalogoReal
   en datos.js), no de datos simulados -- así lo que se sugiere siempre
   existe de verdad en los resultados. */
export function calcularSugerencias(s) {
  const q = s.query.trim().toLowerCase();
  const sugg = [];
  if (q.length >= 2 && s.screen === "home") {
    valoresUnicosCatalogo("municipio").forEach(m => { if (m.toLowerCase().includes(q)) sugg.push({ label: m, kind: "Municipio", term: m }); });
    valoresUnicosCatalogo("estado").forEach(es => { if (es.toLowerCase().includes(q)) sugg.push({ label: es, kind: "Estado", term: es }); });
    valoresUnicosCatalogo("specialty").forEach(sp => { if (sp.toLowerCase().includes(q)) sugg.push({ label: sp, kind: "Especialidad", term: sp }); });
    valoresUnicosCatalogo("name").forEach(n => { if (n.toLowerCase().includes(q)) sugg.push({ label: n, kind: "Médico", term: n }); });
  }
  return sugg.slice(0, 6);
}

/* ---------- Valores calculados (equivalente a renderVals del original) ---------- */
export function calcular(s) {
  const f = s.filters;
  const estadoObj = ESTADOS.find(x => x.name === s.estado);
  const formEstado = ESTADOS.find(x => x.name === s.form.estado) || ESTADOS[0];
  const info = s.screen === "results" || s.screen === "compare" ? raw(s) : { list: [], label: "", sub: "" };
  const listed = s.screen === "results" ? visible(s) : [];
  const d = s.detail;
  const vs = s.cedulaStatus;
  const compareItems = visible(s).filter(x => s.compare.indexOf(x.id) >= 0);

  const coverageRaw = ESTADOS.map(x => ({ name: x.name, total: x.municipios.reduce((acc, m) => acc + num(x.name + m, "cov", 12, 68), 0) }));
  const maxCov = Math.max.apply(null, coverageRaw.map(c => c.total));
  const specTotals = SPECIALTIES.map(sp => ({ name: sp, total: num(sp, "count", 6, 48) }));
  const pending = s.requests.filter(r => r.status === "En revisión").length;

  // Agenda: 7 días a partir de hoy, con los horarios libres de cada uno.
  const bookingDayIndex = s.bookingDay == null ? 0 : s.bookingDay;
  const days = [];
  const today = new Date();
  for (let i = 0; i < 7; i++) {
    const date = new Date(today.getTime() + i * 86400000);
    const slots = slotsFor(d, i);
    days.push({
      indice: i,
      dow: DOW[date.getDay()], num: String(date.getDate()),
      slots: slots.length ? slots.length + " horarios" : "sin cupo",
      disabled: slots.length === 0,
      elegido: i === bookingDayIndex,
    });
  }
  const daySlots = slotsFor(d, bookingDayIndex).map(sl => ({ label: sl, elegido: sl === s.bookingSlot }));
  const selDay = days[bookingDayIndex];

  return {
    screen: s.screen,
    breadcrumb: { home: "Inicio", register: "Inicio / Alta de médico", admin: "Inicio / Solicitudes", metrics: "Inicio / Métricas", compare: "Inicio / Comparar" }[s.screen]
      || (s.screen === "zone" ? "Inicio / " + s.specialty : "Inicio / " + (s.searchTerm ? "Búsqueda" : s.specialty + " / " + s.municipio)),
    pendingBadge: pending ? "(" + pending + ")" : "",
    gridAmplia: PROPS.gridDensity === "amplia",

    // Inicio
    specialties: SPECIALTIES.map((name, i) => ({
      name, num: String(i + 1).padStart(2, "0"),
      meta: PROPS.mostrarConteo === false ? "Ver disponibilidad" : num(name, "count", 6, 48) + " especialistas · " + num(name, "z", 4, 12) + " zonas",
    })),
    totalNote: SPECIALTIES.length + " especialidades · " + ESTADOS.length + " estados",
    query: s.query,
    suggestions: calcularSugerencias(s),
    recent: s.recent,

    // Zona
    specialty: s.specialty,
    estados: ESTADOS.map(x => ({ name: x.name, count: x.municipios.length + " municipios", elegido: x.name === s.estado })),
    hasEstado: !!estadoObj,
    municipios: (estadoObj ? estadoObj.municipios : []).map(m => ({ name: m, meta: num(s.specialty + m, "d", 2, 9) + " especialistas disponibles" })),

    // Google Places (simulado)
    syncLabel: s.syncing ? "Sincronizando…" : s.placesSynced ? "Google Places sincronizado" : "Sincronizar con Google Places",
    syncNote: s.placesSynced ? "Se agregaron consultorios importados de Google Places." : "Importa consultorios con ficha en Google.",

    // Resultados
    viewList: s.view === "list", viewMap: s.view === "map",
    priceOptions: PRICE_OPTIONS.map(p => ({ label: p.label, max: p.max, elegido: f.maxPrice === p.max })),
    fHoy: f.hoy, fTele: f.tele, fSeguro: f.seguro, fPlaces: f.soloVerificados, orden: f.orden,
    filterSummary: [f.maxPrice < 9999 ? "≤ $" + f.maxPrice : null, f.hoy ? "hoy" : null, f.tele ? "teleconsulta" : null, f.seguro ? "con convenio" : null, f.soloVerificados ? "solo verificados" : null].filter(Boolean).join(" · ") || "Sin filtros activos",
    countLabel: listed.length + " de " + info.list.length + " especialistas",
    resultsTitle: info.label, resultsSubtitle: info.sub,
    hasResults: listed.length > 0,
    emptyTitle: info.list.length ? "Ningún especialista cumple los filtros." : "Sin especialistas para esta búsqueda.",
    doctors: listed.map(x => ({
      id: x.id, name: x.name, specialty: x.specialty, cedula: x.cedula, clinic: x.clinic,
      address: x.address + ", " + x.municipio, convenio: x.convenio, tele: x.tele,
      availability: x.hoy ? "Disponible hoy" : x.schedule,
      rating: x.rating, price: x.price, distance: x.distance, source: x.source, fromPlaces: x.fromPlaces,
      compared: s.compare.indexOf(x.id) >= 0,
    })),

    // Comparar
    showCompareBar: s.compare.length > 0 && s.screen === "results",
    compareBarLabel: s.compare.length + " seleccionados para comparar (máximo 3)",
    compareSubtitle: compareItems.length + " especialistas · " + info.label,
    compareList: compareItems.map(x => ({ id: x.id, name: x.name })),
    compareRows: [
      { label: "Especialidad", key: "specialty" }, { label: "Consultorio", key: "clinic" },
      { label: "Zona", key: "municipio" }, { label: "Consulta", key: "price" },
      { label: "Calificación", key: "rating" }, { label: "Distancia", key: "distance" },
      { label: "Convenios", key: "convenio" }, { label: "Fuente", key: "source" }
    ].map(r => ({ label: r.label, cells: compareItems.map(x => String(x[r.key])) })),

    // Ficha / agenda
    hasDetail: !!d,
    detailName: d ? d.name : "", detailSpecialty: d ? d.specialty : "", detailCedula: d ? d.cedula : "",
    detailClinic: d ? d.clinic : "", detailAddress: d ? d.address + ", " + d.municipio : "", detailSchedule: d ? d.schedule : "",
    detailPrice: d ? d.price : "", detailPhone: d ? d.phone : "", detailSource: d ? d.source : "", detailConvenio: d ? d.convenio : "",
    detailFromPlaces: d ? d.fromPlaces : false,
    bookingIdle: s.bookingStep === "idle", bookingPick: s.bookingStep === "pick", bookingDone: s.bookingStep === "done",
    bookingDays: days, bookingSlots: daySlots,
    bookingNote: s.bookingSlot ? "Cita: " + (selDay ? selDay.dow + " " + selDay.num : "") + " a las " + s.bookingSlot : "Elige un horario para confirmar.",
    bookingSummary: (selDay ? selDay.dow + " " + selDay.num : "") + " · " + (s.bookingSlot || ""),

    // Métricas
    kpis: [
      { label: "Especialistas activos", value: String(coverageRaw.reduce((a, c) => a + c.total, 0)), note: "Red nacional simulada", icono: "personas", clase: "kpi-total" },
      { label: "Zonas cubiertas", value: String(ESTADOS.reduce((a, x) => a + x.municipios.length, 0)), note: ESTADOS.length + " estados", icono: "ubicacion", clase: "kpi-cita" },
      { label: "Solicitudes en revisión", value: String(pending), note: s.requests.length + " solicitudes totales", icono: "expediente", clase: "kpi-proceso" },
      { label: "Importados de Google", value: s.placesSynced ? "126" : "0", note: s.placesSynced ? "Última sincronización: hoy" : "Sin sincronizar", icono: "nube", clase: "kpi-seguimiento" }
    ],
    coverage: coverageRaw.map(c => ({ name: c.name, value: c.total + " especialistas", width: Math.round(c.total / maxCov * 100) })),
    lowCoverage: specTotals.filter(x => x.total < 20).map(x => ({ name: x.name, value: x.total + " activos" })),

    // Solicitudes
    adminSummary: pending + " en revisión · " + s.requests.length + " solicitudes",
    requests: s.requests.map((r, i) => ({
      indice: i,
      folio: r.folio, name: r.name, specialty: r.specialty, zone: r.zone,
      cedulaCheck: r.status === "Cédula no localizada" ? "No localizada" : r.cedula + " ✓",
      rfcCheck: r.rfc + (r.status === "Cédula no localizada" ? "" : " ✓"),
      status: r.status,
      statusClass: r.status === "Aprobada" || r.status === "Validada" ? "activo" : r.status === "Rechazada" || r.status === "Cédula no localizada" ? "inactivo" : "pendiente",
    })),

    // Alta de médico
    registered: !!s.registered,
    regName: s.registered ? s.registered.name : "", regFolio: s.registered ? s.registered.folio : "",
    form: s.form,
    formMunicipios: formEstado.municipios,
    verifyLabel: vs === "loading" ? "Consultando…" : vs === "valid" ? "Cédula verificada" : "Verificar cédula profesional",
    verifyMessage: { idle: "Sin verificar", loading: "Consultando registro…", valid: "Cédula localizada en el registro", invalid: "Formato inválido: debe tener 7 u 8 dígitos" }[vs],
    verifyClase: vs === "valid" ? "dp-ok" : vs === "invalid" ? "dp-error" : "dp-neutro",
    verified: vs === "valid",
    verifyHolder: s.form.name || "Titular registrado",
    verifyTitle: "Médico Cirujano y Partero · " + s.form.specialty,
    verifyInstitution: pick(["Universidad de Guadalajara", "UNAM", "UANL", "Universidad Autónoma de Yucatán", "BUAP"], s.form.cedula || "x", "u"),
    verifyYear: String(num(s.form.cedula || "x", "y", 1996, 2019)),
    submitNote: vs === "valid" ? "Cédula validada. Puedes enviar la solicitud." : "Verifica la cédula profesional antes de enviar.",

    footerCount: s.placesSynced ? "Fuentes: directorio interno + Google Places" : "Fuente: directorio interno",
  };
}

/* ---------- Piezas comunes ---------- */
const clasePorFuente = (fromPlaces) => (fromPlaces ? "pendiente" : "seguimiento");

function encabezado({ volver, accionVolver, titulo, texto, extra = "", idTexto = "" }) {
  return `
    <div class="dp-encabezado${extra ? " dp-encabezado-acciones" : ""}">
      <div class="dp-encabezado-texto">
        <button class="btn dp-btn-ghost dp-volver" data-accion="${accionVolver}">${e(volver)}</button>
        <h1 class="dp-titulo">${e(titulo)}</h1>
        <p class="dp-texto"${idTexto ? ` id="${idTexto}"` : ""}>${e(texto)}</p>
      </div>
      ${extra}
    </div>`;
}

/* ---------- Barra propia del directorio ---------- */
export function barra(v) {
  const solicitudes = ("Solicitudes " + v.pendingBadge).trim();
  return `
    <button class="dp-marca" data-accion="ir-inicio">
      ${ICONOS.ubicacion}<span>Directorio de proveedores</span>
    </button>
    <div class="dp-barra-derecha">
      <span class="dp-migas">${e(v.breadcrumb)}</span>
      <button class="btn dp-btn-ghost" data-accion="ir-metricas">Métricas</button>
      <button class="btn dp-btn-ghost" data-accion="ir-solicitudes">${e(solicitudes)}</button>
      <button class="btn btn-secondary" data-accion="ir-alta">Alta de médico</button>
    </div>`;
}

export function pie(v) {
  return `
    <span>Datos simulados para prototipo. Validación de cédula, agenda y Google Places sin conexión real.</span>
    <span>${e(v.footerCount)}</span>`;
}

export function barraComparar(v) {
  return `
    <span>${e(v.compareBarLabel)}</span>
    <div class="dp-acciones">
      <button class="btn btn-primary" data-accion="abrir-comparar">Comparar</button>
      <button class="btn dp-btn-ghost dp-btn-claro" data-accion="quitar-comparar">Quitar todos</button>
    </div>`;
}

/* ---------- Inicio ---------- */
export function sugerencias(lista) {
  if (!lista.length) return "";
  return `
    <div class="dp-sugerencias">
      ${lista.map(sg => `
        <button class="dp-sugerencia" data-accion="buscar-termino" data-valor="${e(sg.term)}">
          <span>${e(sg.label)}</span>
          <span class="dp-etiqueta">${e(sg.kind)}</span>
        </button>`).join("")}
    </div>`;
}

export function pantallaInicio(v) {
  const recientes = v.recent.length ? `
    <div class="dp-recientes">
      <span class="dp-etiqueta">Recientes</span>
      ${v.recent.map(r => `<button class="dp-chip" data-accion="buscar-termino" data-valor="${e(r)}">${e(r)}</button>`).join("")}
    </div>` : "";
  return `
    <div class="card tono-azul">
      <div class="card-body dp-hero">
        <div>
          <h1 class="dp-titulo dp-titulo-hero">Busca al especialista<br>por zona y especialidad</h1>
          <p class="dp-texto dp-texto-hero">Red de proveedores verificados con cédula profesional. Elige una especialidad para acotar por estado y municipio, o busca directamente por zona.</p>
        </div>
        <div class="dp-hero-busqueda">
          <div class="field dp-campo dp-campo-busqueda">
            <label for="dp-q">Buscar por zona, especialidad o nombre</label>
            <div class="dp-fila-busqueda">
              <input type="text" id="dp-q" placeholder="Guadalajara, Mérida, Cardiología…" value="${e(v.query)}" autocomplete="off">
              <button class="btn btn-primary" data-accion="buscar">Buscar</button>
            </div>
            <div id="dp-sugerencias">${sugerencias(v.suggestions)}</div>
          </div>
          ${recientes}
          <div class="dp-sync">
            <button class="btn btn-secondary" data-accion="sincronizar">${e(v.syncLabel)}</button>
            <span class="dp-nota">${e(v.syncNote)}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card tono-verdeazul">
      <div class="card-header">
        <h2>Especialidades médicas</h2>
        <span class="dp-nota">${e(v.totalNote)}</span>
      </div>
      <div class="card-body">
        <div class="dp-grid-especialidades${v.gridAmplia ? " dp-grid-amplia" : ""}">
          ${v.specialties.map(sp => `
            <button class="dp-opcion dp-tarjeta-especialidad" data-accion="elegir-especialidad" data-valor="${e(sp.name)}">
              <span class="dp-numero">${e(sp.num)}</span>
              <span class="dp-tarjeta-nombre">${e(sp.name)}</span>
              <span class="dp-nota">${e(sp.meta)}</span>
            </button>`).join("")}
        </div>
      </div>
    </div>`;
}

/* ---------- Zona: estado y municipio ---------- */
export function pantallaZona(v) {
  const municipios = v.hasEstado ? `
    <div class="dp-grid-municipios">
      ${v.municipios.map(m => `
        <button class="dp-opcion dp-tarjeta-municipio" data-accion="elegir-municipio" data-valor="${e(m.name)}">
          <span class="dp-tarjeta-nombre">${e(m.name)}</span>
          <span class="dp-nota">${e(m.meta)}</span>
        </button>`).join("")}
    </div>` : `<p class="dp-texto dp-muted">Elige primero un estado en la columna izquierda.</p>`;
  return `
    ${encabezado({
      volver: "← Todas las especialidades", accionVolver: "ir-inicio",
      titulo: v.specialty, texto: "Selecciona estado y municipio para ver los especialistas disponibles en la zona.",
    })}
    <div class="dp-dos-columnas dp-zona">
      <div class="card tono-azul">
        <div class="card-header"><h2>Estado</h2></div>
        <div class="card-body">
          <div class="dp-lista-opciones">
            ${v.estados.map(x => `
              <button class="dp-opcion dp-opcion-fila${x.elegido ? " dp-sel" : ""}" data-accion="elegir-estado" data-valor="${e(x.name)}">
                <span>${e(x.name)}</span>
                <span class="dp-nota">${e(x.count)}</span>
              </button>`).join("")}
          </div>
        </div>
      </div>
      <div class="card tono-verdeazul">
        <div class="card-header"><h2>Municipio</h2></div>
        <div class="card-body">${municipios}</div>
      </div>
    </div>`;
}

/* ---------- Resultados ---------- */
// El esqueleto se pinta una sola vez al entrar a Resultados; después solo se
// repintan sus partes, para que el iframe del mapa no se recargue.
export function esqueletoResultados() {
  return `
    <div id="dp-res-cabecera"></div>
    <div class="dp-resultados">
      <aside class="card tono-azul dp-filtros">
        <div class="card-body" id="dp-res-filtros"></div>
      </aside>
      <div class="card tono-verdeazul dp-panel-resultados">
        <div class="card-header" id="dp-res-conteo"></div>
        <div class="card-body">
          <div class="dp-mapa hidden" id="dp-res-mapa"></div>
          <div id="dp-res-lista"></div>
        </div>
      </div>
    </div>`;
}

export function cabeceraResultados(v) {
  const acciones = `
    <div class="dp-acciones">
      <div class="dp-seg" role="group" aria-label="Vista">
        <button class="dp-seg-opcion${v.viewList ? " dp-sel" : ""}" data-accion="vista-lista">Lista</button>
        <button class="dp-seg-opcion${v.viewMap ? " dp-sel" : ""}" data-accion="vista-mapa">Mapa</button>
      </div>
      <button class="btn btn-secondary" data-accion="sincronizar">${e(v.syncLabel)}</button>
      <button class="btn btn-primary" data-accion="ir-inicio">Nueva búsqueda</button>
    </div>`;
  return encabezado({
    volver: "← Cambiar zona", accionVolver: "volver-zona",
    titulo: v.resultsTitle, texto: v.resultsSubtitle, extra: acciones,
  });
}

export function filtrosResultados(v) {
  const casilla = (filtro, marcado, texto) => `
    <label class="dp-check"><input type="checkbox" data-filtro="${filtro}"${marcado ? " checked" : ""}> ${e(texto)}</label>`;
  const opcionOrden = (valor, texto) => `<option value="${valor}"${v.orden === valor ? " selected" : ""}>${e(texto)}</option>`;
  return `
    <div class="dp-seccion">
      <h2 class="dp-subtitulo">Precio máximo</h2>
      <div class="dp-lista-opciones">
        ${v.priceOptions.map(p => `
          <button class="dp-opcion dp-opcion-compacta${p.elegido ? " dp-sel" : ""}" data-accion="precio" data-valor="${p.max}">${e(p.label)}</button>`).join("")}
      </div>
    </div>
    <div class="dp-seccion dp-seccion-linea">
      <h2 class="dp-subtitulo">Filtros</h2>
      ${casilla("hoy", v.fHoy, "Disponible hoy")}
      ${casilla("tele", v.fTele, "Teleconsulta")}
      ${casilla("seguro", v.fSeguro, "Con convenio / seguro")}
      ${casilla("soloVerificados", v.fPlaces, "Solo directorio verificado")}
    </div>
    <div class="field dp-campo dp-seccion-linea">
      <label for="dp-orden">Ordenar por</label>
      <select id="dp-orden">
        ${opcionOrden("rating", "Mejor calificación")}
        ${opcionOrden("precio", "Precio más bajo")}
        ${opcionOrden("cercania", "Más cercano")}
      </select>
    </div>
    <button class="btn dp-btn-ghost" data-accion="limpiar-filtros">Limpiar filtros</button>`;
}

export function conteoResultados(v) {
  return `<h2>${e(v.countLabel)}</h2><span class="dp-nota">${e(v.filterSummary)}</span>`;
}

export function listaResultados(v) {
  if (!v.hasResults) {
    return `
      <div class="dp-vacio">
        <p class="dp-vacio-titulo">${e(v.emptyTitle)}</p>
        <p class="dp-texto">Prueba con otro municipio, relaja los filtros o sincroniza con Google Places para ampliar la cobertura.</p>
        <div class="dp-acciones">
          <button class="btn btn-secondary" data-accion="limpiar-filtros">Limpiar filtros</button>
          <button class="btn btn-primary" data-accion="sincronizar">${e(v.syncLabel)}</button>
        </div>
      </div>`;
  }
  return v.doctors.map(d => `
    <article class="dp-medico">
      <div class="dp-medico-principal">
        <div class="dp-medico-nombre">
          <h3>${e(d.name)}</h3>
          <span class="badge ${clasePorFuente(d.fromPlaces)}">${e(d.source)}</span>
          ${d.tele ? `<span class="badge espera">Teleconsulta</span>` : ""}
        </div>
        <p class="dp-nota">${e(d.specialty)} · Cédula ${e(d.cedula)} · ${e(d.convenio)}</p>
      </div>
      <div class="dp-medico-consultorio">
        <div class="dp-fuerte">${e(d.clinic)}</div>
        <div class="dp-muted">${e(d.address)}</div>
      </div>
      <div class="dp-medico-disponibilidad">
        <div>${e(d.availability)}</div>
        <div class="dp-muted"><span class="dp-dato">${e(d.rating)}</span> · <span class="dp-dato">${e(d.price)}</span> · <span class="dp-dato">${e(d.distance)}</span></div>
      </div>
      <div class="dp-medico-acciones">
        <label class="dp-check dp-check-compacto"><input type="checkbox" data-accion="comparar" data-id="${e(d.id)}"${d.compared ? " checked" : ""}> Comparar</label>
        <button class="btn btn-secondary" data-accion="ficha" data-id="${e(d.id)}">Ver ficha</button>
      </div>
    </article>`).join("");
}

/* ---------- Comparar ---------- */
export function pantallaComparar(v) {
  return `
    ${encabezado({
      volver: "← Volver a resultados", accionVolver: "volver-resultados",
      titulo: "Comparar especialistas", texto: v.compareSubtitle,
    })}
    <div class="card tono-verdeazul">
      <div class="table-wrap">
        <table class="dp-tabla-comparar">
          <thead>
            <tr>
              <th class="dp-col-criterio">Criterio</th>
              ${v.compareList.map(c => `<th>${e(c.name)}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${v.compareRows.map(row => `
              <tr>
                <td class="dp-fuerte">${e(row.label)}</td>
                ${row.cells.map(cell => `<td>${e(cell)}</td>`).join("")}
              </tr>`).join("")}
            <tr>
              <td></td>
              ${v.compareList.map(c => `<td><button class="btn btn-primary" data-accion="agendar-desde-comparar" data-id="${e(c.id)}">Agendar cita</button></td>`).join("")}
            </tr>
          </tbody>
        </table>
      </div>
    </div>`;
}

/* ---------- Métricas ---------- */
export function pantallaMetricas(v) {
  return `
    ${encabezado({
      volver: "← Volver al directorio", accionVolver: "ir-inicio",
      titulo: "Métricas del directorio", texto: "Cobertura por estado y especialidades con oferta insuficiente.",
    })}
    <div class="kpi-row">
      ${v.kpis.map(k => `
        <div class="kpi-card ${k.clase}">
          <div class="kpi-icon">${ICONO_KPI[k.icono]}</div>
          <div class="kpi-info">
            <div class="kpi-value">${e(k.value)}</div>
            <div class="kpi-label">${e(k.label)}</div>
            <div class="dp-nota">${e(k.note)}</div>
          </div>
        </div>`).join("")}
    </div>
    <div class="dp-dos-columnas dp-metricas">
      <div class="card tono-azul">
        <div class="card-header"><h2>Especialistas por estado</h2></div>
        <div class="card-body dp-cobertura">
          ${v.coverage.map(c => `
            <div>
              <div class="dp-cobertura-fila">
                <span class="dp-fuerte">${e(c.name)}</span>
                <span class="dp-muted">${e(c.value)}</span>
              </div>
              <div class="dp-pista"><div class="dp-pista-valor" style="width:${Number(c.width)}%;"></div></div>
            </div>`).join("")}
        </div>
      </div>
      <div class="card tono-ambar">
        <div class="card-header"><h2>Baja cobertura</h2></div>
        <div class="card-body">
          <div class="dp-lista-opciones">
            ${v.lowCoverage.map(l => `
              <div class="dp-renglon">
                <span class="dp-fuerte">${e(l.name)}</span>
                <span class="dp-valor-alerta">${e(l.value)}</span>
              </div>`).join("")}
          </div>
          <p class="hint dp-umbral">Umbral de alerta: menos de 20 especialistas activos en la red nacional.</p>
        </div>
      </div>
    </div>`;
}

/* ---------- Solicitudes de alta ---------- */
export function pantallaSolicitudes(v) {
  return `
    ${encabezado({
      volver: "← Volver al directorio", accionVolver: "ir-inicio",
      titulo: "Solicitudes de alta", texto: "Validación de cédula profesional (RNP) y cédula fiscal (SAT) por solicitud.",
      extra: `<span class="dp-nota">${e(v.adminSummary)}</span>`,
    })}
    <div class="card tono-verdeazul">
      <div class="table-wrap">
        <table class="mini-table dp-tabla-solicitudes">
          <thead>
            <tr>
              <th>Folio</th><th>Médico</th><th>Especialidad</th><th>Zona</th><th>Cédula prof.</th><th>RFC</th><th>Estatus</th><th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${v.requests.map(r => `
              <tr>
                <td data-label="Folio" class="dp-tabular">${e(r.folio)}</td>
                <td data-label="Médico" class="dp-fuerte">${e(r.name)}</td>
                <td data-label="Especialidad">${e(r.specialty)}</td>
                <td data-label="Zona">${e(r.zone)}</td>
                <td data-label="Cédula prof.">${e(r.cedulaCheck)}</td>
                <td data-label="RFC">${e(r.rfcCheck)}</td>
                <td data-label="Estatus"><span class="badge ${r.statusClass}">${e(r.status)}</span></td>
                <td data-label="Acciones">
                  <div class="dp-acciones">
                    <button class="btn btn-primary" data-accion="aprobar" data-indice="${r.indice}">Aprobar</button>
                    <button class="btn btn-secondary" data-accion="rechazar" data-indice="${r.indice}">Rechazar</button>
                  </div>
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>`;
}

/* ---------- Alta de médico ---------- */
// Partes del formulario que dependen de lo que se escribe: se repintan solas
// (sin tocar los campos) para no perder el foco ni el cursor.
export function altaVerificacion(v) {
  return `
    <button class="btn btn-primary" data-accion="verificar-cedula">${e(v.verifyLabel)}</button>
    <span class="dp-mensaje ${v.verifyClase}">${e(v.verifyMessage)}</span>`;
}

export function altaPanelCedula(v) {
  if (!v.verified) return "";
  const dato = (titulo, valor) => `<div><dt>${e(titulo)}</dt><dd>${e(valor)}</dd></div>`;
  return `
    <div class="dp-panel-cedula">
      <span class="badge seguimiento">Cédula válida</span>
      <dl class="dp-datos">
        ${dato("Titular", v.verifyHolder)}
        ${dato("Título", v.verifyTitle)}
        ${dato("Institución", v.verifyInstitution)}
        ${dato("Año de registro", v.verifyYear)}
      </dl>
    </div>`;
}

export function altaNota(v) {
  return e(v.submitNote);
}

export function opcionesMunicipio(v) {
  return v.formMunicipios.map(m => `<option value="${e(m)}"${m === v.form.municipio ? " selected" : ""}>${e(m)}</option>`).join("");
}

export function pantallaAlta(v) {
  const cabecera = encabezado({
    volver: "← Volver al directorio", accionVolver: "ir-inicio",
    titulo: "Alta de médico",
    texto: "Registra tu consultorio en el directorio. La cédula profesional se valida contra el Registro Nacional de Profesionistas y la cédula fiscal (RFC) contra el padrón del SAT.",
  });
  if (v.registered) {
    return `
      ${cabecera}
      <div class="card tono-verde dp-confirmacion">
        <div class="card-body">
          <span class="badge seguimiento">Solicitud recibida</span>
          <h2 class="dp-titulo dp-titulo-medio">${e(v.regName)} quedó en revisión</h2>
          <p class="dp-texto">Folio ${e(v.regFolio)}. Cédula profesional validada. Puedes seguir el estatus en la bandeja de solicitudes.</p>
          <div class="dp-acciones">
            <button class="btn btn-primary" data-accion="ir-solicitudes">Ver solicitudes</button>
            <button class="btn btn-secondary" data-accion="registrar-otro">Registrar otro médico</button>
          </div>
        </div>
      </div>`;
  }
  const f = v.form;
  const campo = (id, campoForm, etiqueta, placeholder) => `
    <div class="field dp-campo">
      <label for="${id}">${e(etiqueta)}</label>
      <input type="text" id="${id}" data-campo="${campoForm}" placeholder="${e(placeholder)}" value="${e(f[campoForm])}" autocomplete="off">
    </div>`;
  const opciones = (lista, elegido) => lista.map(x => `<option value="${e(x)}"${x === elegido ? " selected" : ""}>${e(x)}</option>`).join("");
  return `
    ${cabecera}
    <div class="dp-dos-columnas dp-alta">
      <div class="card tono-azul">
        <div class="card-body dp-formulario">
          <div class="dp-grid-campos">
            ${campo("dp-nombre", "name", "Nombre completo", "Dra. Laura Méndez Ruiz")}
            <div class="field dp-campo">
              <label for="dp-esp">Especialidad</label>
              <select id="dp-esp" data-campo="specialty">${opciones(SPECIALTIES, f.specialty)}</select>
            </div>
          </div>
          <div class="dp-grid-campos">
            ${campo("dp-ced", "cedula", "Cédula profesional", "8 dígitos")}
            ${campo("dp-rfc", "rfc", "Cédula fiscal (RFC)", "MERL850214H23")}
          </div>
          <div class="dp-verificacion" id="dp-alta-verificacion">${altaVerificacion(v)}</div>
          <div class="dp-grid-campos">
            <div class="field dp-campo">
              <label for="dp-estado-sel">Estado</label>
              <select id="dp-estado-sel" data-campo="estado">${opciones(ESTADOS.map(x => x.name), f.estado)}</select>
            </div>
            <div class="field dp-campo">
              <label for="dp-mun-sel">Municipio</label>
              <select id="dp-mun-sel" data-campo="municipio">${opcionesMunicipio(v)}</select>
            </div>
          </div>
          ${campo("dp-dir", "address", "Dirección del consultorio", "Av. Vallarta 1450, Col. Americana")}
          <div class="dp-grid-campos">
            ${campo("dp-tel", "phone", "Teléfono", "33 1234 5678")}
            ${campo("dp-mail", "email", "Correo electrónico", "consultorio@correo.mx")}
          </div>
          <div class="dp-acciones dp-enviar">
            <button class="btn btn-primary" data-accion="enviar-alta">Enviar solicitud de alta</button>
            <span class="dp-nota" id="dp-alta-nota">${altaNota(v)}</span>
          </div>
        </div>
      </div>
      <aside class="card tono-morado">
        <div class="card-body dp-lateral">
          <div>
            <h3 class="dp-subtitulo">Validación de cédula</h3>
            <p class="dp-texto">La consulta se hace contra el servicio de Cédula Profesional (SEP/RNP) por número de cédula. En esta demo la respuesta está simulada: cualquier número de 7 u 8 dígitos se valida.</p>
          </div>
          <div id="dp-alta-panel">${altaPanelCedula(v)}</div>
          <div class="dp-seccion-linea">
            <h3 class="dp-subtitulo">Documentos requeridos</h3>
            <ul class="dp-documentos">
              <li>Cédula profesional (frente)</li>
              <li>Constancia de situación fiscal</li>
              <li>Comprobante de domicilio del consultorio</li>
              <li>Póliza de responsabilidad civil (opcional)</li>
            </ul>
          </div>
        </div>
      </aside>
    </div>`;
}

/* ---------- Ficha del médico y agenda (modal) ---------- */
export function fichaCuerpo(v) {
  const cabecera = `
    <span class="badge ${clasePorFuente(v.detailFromPlaces)}">${e(v.detailSource)}</span>
    <p class="dp-ficha-sub">${e(v.detailSpecialty)} · Cédula ${e(v.detailCedula)}</p>`;
  if (v.bookingPick) {
    return `
      ${cabecera}
      <div class="dp-ficha-seccion">
        <h3 class="dp-subtitulo">Elige día</h3>
        <div class="dp-dias">
          ${v.bookingDays.map(day => `
            <button class="dp-opcion dp-dia${day.elegido ? " dp-sel" : ""}" data-accion="elegir-dia" data-indice="${day.indice}"${day.disabled ? " disabled" : ""}>
              <span class="dp-etiqueta">${e(day.dow)}</span>
              <span class="dp-dia-num">${e(day.num)}</span>
              <span class="dp-dia-cupo">${e(day.slots)}</span>
            </button>`).join("")}
        </div>
        <h3 class="dp-subtitulo dp-subtitulo-espacio">Horarios disponibles</h3>
        <div class="dp-horarios">
          ${v.bookingSlots.map(sl => `
            <button class="dp-horario${sl.elegido ? " dp-sel" : ""}" data-accion="elegir-horario" data-valor="${e(sl.label)}">${e(sl.label)}</button>`).join("")}
        </div>
      </div>`;
  }
  if (v.bookingDone) {
    return `
      ${cabecera}
      <div class="dp-ficha-seccion">
        <span class="badge seguimiento">Cita confirmada</span>
        <p class="dp-cita-resumen">${e(v.bookingSummary)}</p>
        <p class="dp-texto">${e(v.detailClinic)} · ${e(v.detailAddress)}. Recibirás la confirmación y el recordatorio por correo.</p>
      </div>`;
  }
  const dato = (titulo, valor) => `<div><dt>${e(titulo)}</dt><dd>${e(valor)}</dd></div>`;
  return `
    ${cabecera}
    <dl class="dp-ficha-datos">
      ${dato("Consultorio", v.detailClinic)}
      ${dato("Dirección", v.detailAddress)}
      ${dato("Horario", v.detailSchedule)}
      ${dato("Consulta", v.detailPrice)}
      ${dato("Convenios", v.detailConvenio)}
      ${dato("Teléfono", v.detailPhone)}
    </dl>`;
}

export function fichaPie(v) {
  if (v.bookingPick) {
    return `
      <button class="btn btn-primary" data-accion="confirmar-cita">Confirmar cita</button>
      <button class="btn btn-secondary" data-accion="volver-ficha">Volver</button>
      <span class="dp-nota">${e(v.bookingNote)}</span>`;
  }
  if (v.bookingDone) {
    return `<button class="btn btn-secondary" data-accion="cerrar-ficha">Cerrar</button>`;
  }
  return `
    <button class="btn btn-primary" data-accion="agendar">Agendar cita</button>
    <button class="btn btn-secondary" data-accion="cerrar-ficha">Cerrar</button>`;
}
