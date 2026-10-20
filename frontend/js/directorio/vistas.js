/* Directorio de Proveedores (maqueta): cálculo de lo que se pinta y
   plantillas HTML de cada sub-pantalla.

   calcular(estado) es el equivalente de renderVals() del prototipo
   original: a partir del estado arma todos los textos y listas (mismas
   fórmulas, mismos textos). Las plantillas solo acomodan esos valores con
   el diseño del portal (tarjetas, botones, tablas, badges). Todo texto
   pasa por escapeHtml; los clics se resuelven por delegación con
   data-accion (ver pantallas/directorio-proveedores.js). */
import { escapeHtml as e } from "../core/formato.js";
import { esPerfilAdministrador } from "../core/sesion.js";

/* Estatus en los que una solicitud de alta todavía se puede corregir --
   mismo criterio que ESTATUS_EDITABLES en
   app/repositories/solicitudes_alta_medico_repo.py (el backend lo exige
   igual: editar una ya resuelta responde 409). */
const ESTATUS_EDITABLES = ["En revisión", "Cédula no localizada"];
import { ICONOS } from "../componentes/iconos.js";
import {
  ESTADOS, PRICE_OPTIONS, PROPS,
  num, pick, raw, visible, valoresUnicosCatalogo,
  entidadesAltaCache, municipiosAltaCache,
  especialidadesKpiCache, todasLasEspecialidades,
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

/* El KPI que lleva cada tarjeta de especialidad: cuántos proveedores del
   padrón hay dentro y fuera de la red (formato que pidió el usuario,
   2026-10-20). Los conteos son reales -- salen de amarrar cada proveedor a
   una especialidad del catálogo, ver app/repositories/especialidades_repo.py.

   Una especialidad en 0 no se esconde: se marca "Sin proveedores" y se deja
   clickeable, porque justo esa es la que hay que salir a contratar (ahí
   entra "Buscar fuera de la red"). */
function kpiEspecialidad(x) {
  const dentro = Number(x.dentro_de_red) || 0;
  const fuera = Number(x.fuera_de_red) || 0;
  if (dentro + fuera === 0) return "Sin proveedores";
  return dentro + " dentro de la red · " + fuera + " fuera";
}

function tarjetaEspecialidad(x, i) {
  return {
    id: x.cl_especialidad,
    name: x.descripcion,
    // Consecutivo de la POSICIÓN en pantalla (01..16), no el ordenKPI del
    // catálogo: ese trae huecos y un valor repetido, así que numerar con él
    // se vería como un error ("15" dos veces, sin "06" ni "10").
    num: String(i + 1).padStart(2, "0"),
    meta: kpiEspecialidad(x),
    vacia: (Number(x.dentro_de_red) || 0) + (Number(x.fuera_de_red) || 0) === 0,
  };
}

/* Colonia, código postal y zona del domicilio de consulta (la calle va
   aparte, en su propio renglón). */
function _domicilioResto(x) {
  return [
    x.colonia,
    x.codigoPostal ? "C.P. " + x.codigoPostal : "",
    [x.municipio, x.estado].filter(Boolean).join(", "),
  ].filter(Boolean).join(" · ");
}

/* ---------- Valores calculados (equivalente a renderVals del original) ---------- */
export function calcular(s) {
  const f = s.filters;
  const estadoObj = ESTADOS.find(x => x.name === s.estado);
  const info = s.screen === "results" || s.screen === "compare" ? raw(s) : { list: [], label: "", sub: "" };
  const listed = s.screen === "results" ? visible(s) : [];
  const d = s.detail;
  const vs = s.cedulaStatus;
  const compareItems = visible(s).filter(x => s.compare.indexOf(x.id) >= 0);
  const esAdministrador = esPerfilAdministrador();

  const coverageRaw = ESTADOS.map(x => ({ name: x.name, total: x.municipios.reduce((acc, m) => acc + num(x.name + m, "cov", 12, 68), 0) }));
  const maxCov = Math.max.apply(null, coverageRaw.map(c => c.total));
  // Catálogo real de especialidades, ya partido por el servidor en lo que
  // cabe en pantalla (16 = 4 renglones de 4) y lo que va al combo.
  const catalogoEsp = especialidadesKpiCache();
  const specTotals = todasLasEspecialidades().map(x => ({
    name: x.descripcion,
    total: (Number(x.dentro_de_red) || 0) + (Number(x.fuera_de_red) || 0),
  }));
  const pending = s.requests.filter(r => r.status === "En revisión").length;

  // Agenda: los días y horarios REALMENTE libres los manda el servidor (ver
  // cargarAgenda en datos.js) -- s.agenda llega vacío mientras se consulta.
  const bookingDayIndex = s.bookingDay == null ? 0 : s.bookingDay;
  const days = (s.agenda || []).map((dia, i) => ({
    indice: i,
    dow: dia.dia_semana, num: String(dia.dia_mes), fecha: dia.fecha,
    slots: dia.horarios.length ? dia.horarios.length + " horarios" : "sin cupo",
    disabled: dia.horarios.length === 0,
    elegido: i === bookingDayIndex,
  }));
  const diaElegido = (s.agenda || [])[bookingDayIndex];
  const daySlots = (diaElegido ? diaElegido.horarios : []).map(sl => ({ label: sl, elegido: sl === s.bookingSlot }));
  const selDay = days[bookingDayIndex];

  return {
    screen: s.screen,
    breadcrumb: { home: "Inicio", register: "Inicio / Alta de médico", admin: "Inicio / Solicitudes", metrics: "Inicio / Métricas", compare: "Inicio / Comparar" }[s.screen]
      || (s.screen === "zone" ? "Inicio / " + s.specialty : "Inicio / " + (s.searchTerm ? "Búsqueda" : s.specialty + " / " + s.municipio)),
    pendingBadge: pending ? "(" + pending + ")" : "",
    gridAmplia: PROPS.gridDensity === "amplia",

    // Inicio
    specialties: catalogoEsp.tarjetas.map(tarjetaEspecialidad),
    // Las que no caben en la cuadrícula siguen disponibles aquí, con la
    // misma funcionalidad que una tarjeta (instrucción del usuario).
    specialtyCombo: catalogoEsp.combo.map(x => ({
      id: x.cl_especialidad,
      name: x.descripcion,
      meta: kpiEspecialidad(x),
      elegido: x.cl_especialidad === s.specialtyId,
    })),
    specialtyComboNota: catalogoEsp.combo.length
      ? catalogoEsp.combo.length + " especialidades más, fuera de las " + catalogoEsp.tarjetas.length + " de mayor prioridad"
      : "",
    cargandoEspecialidades: catalogoEsp.total === 0,
    totalNote: catalogoEsp.total
      ? catalogoEsp.total + " especialidades · " + catalogoEsp.tarjetas.length + " en pantalla"
      : "Cargando catálogo…",
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
      id: x.id, clave: x.clave, name: x.name, specialty: x.specialty, cedula: x.cedula, clinic: x.clinic,
      // Domicilio DONDE DA LA CONSULTA, en dos renglones: primero la calle
      // con sus números y luego colonia / CP / municipio.
      domicilioCalle: x.calleNumExtInt || "Domicilio no especificado",
      domicilioResto: _domicilioResto(x),
      convenio: x.convenio, tele: x.tele, origen: x.origen,
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
    detailClinic: d ? d.clinic : "", detailSchedule: d ? d.schedule : "",
    detailDomicilioCalle: d ? (d.calleNumExtInt || "Domicilio no especificado") : "",
    detailDomicilioResto: d ? _domicilioResto(d) : "",
    detailPrice: d ? d.price : "", detailPhone: d ? d.phone : "", detailSource: d ? d.source : "", detailConvenio: d ? d.convenio : "",
    detailClave: d ? d.clave : "", detailOrigen: d ? d.origen : "",
    bookingIdle: s.bookingStep === "idle", bookingPick: s.bookingStep === "pick", bookingDone: s.bookingStep === "done",
    bookingDays: days, bookingSlots: daySlots,
    bookingNote: s.bookingGuardando
      ? "Agendando…"
      : s.bookingSlot
        ? "Cita: " + (selDay ? selDay.dow + " " + selDay.num : "") + " a las " + s.bookingSlot
        : "Elige un horario para confirmar.",
    bookingSummary: (selDay ? selDay.dow + " " + selDay.num : "") + " · " + (s.bookingSlot || ""),
    bookingFolio: s.bookingFolio || "",
    bookingGuardando: !!s.bookingGuardando,

    // Métricas
    kpis: [
      { label: "Especialistas activos", value: String(coverageRaw.reduce((a, c) => a + c.total, 0)), note: "Red nacional simulada", icono: "personas", clase: "kpi-total" },
      { label: "Zonas cubiertas", value: String(ESTADOS.reduce((a, x) => a + x.municipios.length, 0)), note: ESTADOS.length + " estados", icono: "ubicacion", clase: "kpi-cita" },
      { label: "Solicitudes en revisión", value: String(pending), note: s.requests.length + " solicitudes totales", icono: "expediente", clase: "kpi-proceso" },
      { label: "Importados de Google", value: s.placesSynced ? "126" : "0", note: s.placesSynced ? "Última sincronización: hoy" : "Sin sincronizar", icono: "nube", clase: "kpi-seguimiento" }
    ],
    coverage: coverageRaw.map(c => ({ name: c.name, value: c.total + " especialistas", width: Math.round(c.total / maxCov * 100) })),
    // Las especialidades con menos proveedores del padrón REAL (antes era un
    // conteo simulado). Se acotan a las 10 peores y ascendente: con el
    // catálogo completo de 38, listar "todas las que tienen menos de 20"
    // sería listarlas casi todas y no diría nada.
    lowCoverage: specTotals
      .slice()
      .sort((a, b) => a.total - b.total || a.name.localeCompare(b.name))
      .slice(0, 10)
      .map(x => ({ name: x.name, value: x.total === 0 ? "sin proveedores" : x.total + " en el padrón" })),

    // Solicitudes
    adminSummary: pending + " en revisión · " + s.requests.length + " solicitudes",
    requests: s.requests.map((r, i) => ({
      indice: i,
      folio: r.folio, name: r.name, specialty: r.specialty, zone: r.zone,
      cedulaCheck: r.status === "Cédula no localizada" ? "No localizada" : r.cedula + " ✓",
      rfcCheck: r.rfc + (r.status === "Cédula no localizada" ? "" : " ✓"),
      status: r.status,
      // La clave que le tocó al aprobarse: es con la que ya se le pueden
      // agendar citas, y la conserva aunque después llegue en la carga.
      claveProveedor: r.claveProveedor || "—",
      // Revisar una solicitud (aprobar, rechazar o corregirla antes) es
      // exclusivo de Administrador; el backend lo exige igual, esto solo
      // evita mostrar botones que iban a responder 403.
      puedeResolver: esAdministrador,
      // Editar solo mientras nadie la haya resuelto -- es decir, mientras
      // siga en revisión o su cédula profesional no se haya localizado en
      // el registro, que es el caso que de verdad hay que poder corregir.
      // Ya aprobada, el proveedor existe en el padrón con su clave y puede
      // tener citas (ver ESTATUS_EDITABLES en el repositorio).
      puedeEditar: esAdministrador && ESTATUS_EDITABLES.includes(r.status),
      statusClass: r.status === "Aprobada" || r.status === "Validada" ? "activo" : r.status === "Rechazada" || r.status === "Cédula no localizada" ? "inactivo" : "pendiente",
    })),

    // Alta de médico (la misma pantalla sirve para capturar un alta nueva y
    // para corregir una solicitud en revisión -- ver editandoFolio).
    registered: !!s.registered,
    regName: s.registered ? s.registered.name : "", regFolio: s.registered ? s.registered.folio : "",
    editando: !!s.editandoFolio,
    editandoFolio: s.editandoFolio || "",
    form: s.form,
    formEntidades: entidadesAltaCache(),
    formMunicipios: municipiosAltaCache(s.form.estado),

    // Búsqueda fuera de la red (DENUE). Usa los catálogos REALES de Entidad
    // y Municipio (los mismos del Alta de médico), no el catálogo de la
    // pantalla Zona -- el DENUE necesita la clave del INEGI, que solo sale
    // de ahí.
    fueraForm: s.fueraForm,
    fueraEntidades: entidadesAltaCache(),
    fueraMunicipios: municipiosAltaCache(s.fueraForm.codEnt),
    fueraBuscando: !!s.fueraBuscando,
    fueraError: s.fueraError || "",
    fueraBuscado: !!s.fueraResultados,
    fueraArea: s.fueraResultados ? s.fueraResultados.area : "",
    fueraFuente: s.fueraResultados ? s.fueraResultados.fuente : "",
    fueraCandidatos: s.fueraResultados ? s.fueraResultados.candidatos : [],
    fueraTipo: s.fueraResultados ? (s.fueraResultados.tipo_descripcion || "") : "",
    fueraPuedeBuscar: !!(s.fueraForm.codEnt && (s.fueraForm.especialidad || "").trim().length >= 3),
    verifyLabel: vs === "loading" ? "Consultando…" : vs === "valid" ? "Cédula verificada" : "Verificar cédula profesional",
    verifyMessage: { idle: "Sin verificar", loading: "Consultando registro…", valid: "Cédula localizada en el registro", invalid: "Formato inválido: debe tener 7 u 8 dígitos" }[vs],
    verifyClase: vs === "valid" ? "dp-ok" : vs === "invalid" ? "dp-error" : "dp-neutro",
    verified: vs === "valid",
    verifyHolder: s.form.name || "Titular registrado",
    verifyTitle: "Médico Cirujano y Partero · " + s.form.specialty,
    verifyInstitution: pick(["Universidad de Guadalajara", "UNAM", "UANL", "Universidad Autónoma de Yucatán", "BUAP"], s.form.cedula || "x", "u"),
    verifyYear: String(num(s.form.cedula || "x", "y", 1996, 2019)),
    submitNote: vs === "valid"
      ? (s.editandoFolio ? "Cédula validada. Puedes guardar los cambios." : "Cédula validada. Puedes enviar la solicitud.")
      : (s.editandoFolio ? "Cambiaste la cédula: vuelve a verificarla antes de guardar." : "Verifica la cédula profesional antes de enviar."),

    footerCount: s.placesSynced ? "Fuentes: directorio interno + Google Places" : "Fuente: directorio interno",
  };
}

/* ---------- Piezas comunes ---------- */
/* Color del distintivo según de dónde salió el proveedor: "Dentro de la red"
   (llegó en la carga) en verde, "Fuera de la red" (alta del portal) en
   ámbar, para que se note de un vistazo cuál ya está contratado. */
const clasePorOrigen = (origen) => (origen === "portal" ? "pendiente" : "seguimiento");

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
    <span>Padrón, altas y citas reales. La validación de cédula y Google Places siguen sin conexión real.</span>
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
        ${v.cargandoEspecialidades
          ? `<div class="spinner-row">Cargando el catálogo de especialidades…</div>`
          : `<div class="dp-grid-especialidades${v.gridAmplia ? " dp-grid-amplia" : ""}">
          ${v.specialties.map(sp => `
            <button class="dp-opcion dp-tarjeta-especialidad${sp.vacia ? " dp-tarjeta-vacia" : ""}" data-accion="elegir-especialidad" data-valor="${e(sp.name)}" data-id="${e(String(sp.id))}">
              <span class="dp-numero">${e(sp.num)}</span>
              <span class="dp-tarjeta-nombre">${e(sp.name)}</span>
              <span class="dp-nota">${e(sp.meta)}</span>
            </button>`).join("")}
        </div>
        ${v.specialtyCombo.length ? `
          <div class="dp-otras-especialidades">
            <div class="field dp-campo">
              <label for="dp-esp-otras">Otras especialidades</label>
              <select id="dp-esp-otras" data-accion-cambio="elegir-especialidad-combo">
                <option value="">Selecciona una especialidad…</option>
                ${v.specialtyCombo.map(sp => `
                  <option value="${e(String(sp.id))}"${sp.elegido ? " selected" : ""}>${e(sp.name)} — ${e(sp.meta)}</option>`).join("")}
              </select>
              <span class="dp-nota">${e(v.specialtyComboNota)}</span>
            </div>
          </div>` : ""}`}
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
        <p class="dp-texto">No hay proveedores <b>dentro de la red</b> que cumplan con esta búsqueda. Puedes relajar los filtros, o buscar consultorios <b>fuera de la red</b> para evaluar su contratación.</p>
        <div class="dp-acciones">
          <button class="btn btn-secondary" data-accion="limpiar-filtros">Limpiar filtros</button>
          <button class="btn btn-primary" data-accion="ir-fuera-de-red">Buscar fuera de la red</button>
        </div>
      </div>`;
  }
  return v.doctors.map(d => `
    <article class="dp-medico">
      <div class="dp-medico-principal">
        <div class="dp-medico-nombre">
          <span class="dp-origen-punto ${d.origen === "portal" ? "portal" : "catalogo"}" title="${e(d.source)}"></span>
          <h3>${e(d.name)}</h3>
          <span class="badge ${clasePorOrigen(d.origen)}">${e(d.source)}</span>
          ${d.tele ? `<span class="badge espera">Teleconsulta</span>` : ""}
        </div>
        <p class="dp-nota">${e(d.specialty)} · Cédula ${e(d.cedula)} · ${e(d.convenio)}</p>
        <p class="dp-nota dp-clave">Clave ${e(d.clave)}</p>
      </div>
      <div class="dp-medico-consultorio">
        <div class="dp-fuerte">${e(d.clinic)}</div>
        <div class="dp-domicilio-etiqueta">Domicilio de consulta</div>
        <div class="dp-muted">${e(d.domicilioCalle)}</div>
        <div class="dp-muted">${e(d.domicilioResto)}</div>
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
          <p class="hint dp-umbral">Las 10 especialidades del catálogo con menos proveedores en el padrón. Son las candidatas a buscar fuera de la red.</p>
        </div>
      </div>
    </div>`;
}

/* ---------- Solicitudes de alta ---------- */
export function pantallaSolicitudes(v) {
  return `
    ${encabezado({
      volver: "← Volver al directorio", accionVolver: "ir-inicio",
      titulo: "Solicitudes de alta",
      texto: "Validación de cédula profesional (RNP) y cédula fiscal (SAT) por solicitud. "
        + "Aprobar, rechazar y corregir una solicitud es exclusivo del perfil Administrador; "
        + "«Editar» solo aparece mientras está sin resolver (en revisión o con la cédula no localizada).",
      extra: `<span class="dp-nota">${e(v.adminSummary)}</span>`,
    })}
    <div class="card tono-verdeazul">
      <div class="table-wrap">
        <table class="mini-table dp-tabla-solicitudes">
          <thead>
            <tr>
              <th>Folio</th><th>Médico</th><th>Especialidad</th><th>Zona</th><th>Cédula prof.</th><th>RFC</th><th>Clave</th><th>Estatus</th><th>Acciones</th>
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
                <td data-label="Clave" class="dp-tabular">${e(r.claveProveedor)}</td>
                <td data-label="Estatus"><span class="badge ${r.statusClass}">${e(r.status)}</span></td>
                <td data-label="Acciones">
                  <div class="dp-acciones">
                    ${r.puedeEditar ? `<button class="btn btn-secondary" data-accion="editar-solicitud" data-indice="${r.indice}">Editar</button>` : ""}
                    ${r.puedeResolver ? `
                      <button class="btn btn-primary" data-accion="aprobar" data-indice="${r.indice}">Aprobar</button>
                      <button class="btn btn-secondary" data-accion="rechazar" data-indice="${r.indice}">Rechazar</button>` : ""}
                    ${!r.puedeResolver && !r.puedeEditar ? `<span class="dp-nota">Solo Administrador</span>` : ""}
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

/* Entidad/Municipio del Alta de médico vienen del catálogo real como
   {clave, descripcion} (CodEnt/dsEntFed, CodMD/dsMunDel) -- el value del
   <option> es la clave (para encadenar el combo), el texto es la
   descripción. Sin opción "Todas": aquí siempre hace falta una entidad
   puntual (a diferencia del filtro de Expedientes). */
function opcionesCatalogoTexto(lista, elegido) {
  return lista.map(it => `<option value="${e(it.clave)}"${it.clave === elegido ? " selected" : ""}>${e(it.descripcion)}</option>`).join("");
}

export function opcionesEntidadAlta(v) {
  return opcionesCatalogoTexto(v.formEntidades, v.form.estado);
}

export function opcionesMunicipio(v) {
  if (!v.form.estado) return `<option value="">Elige un estado primero</option>`;
  if (!v.formMunicipios.length) return `<option value="">Cargando…</option>`;
  return opcionesCatalogoTexto(v.formMunicipios, v.form.municipio);
}

/* El combo de especialidad del alta usa el MISMO catálogo que las tarjetas
   (las 38, en el orden del KPI) -- antes eran 12 nombres fijos en el código,
   así que se podían dar de alta médicos con una especialidad que el catálogo
   no conoce y que por lo tanto no sumaba a ningún KPI. */
export function opcionesEspecialidadAlta(elegida) {
  const lista = todasLasEspecialidades();
  if (!lista.length) return `<option value="">Cargando…</option>`;
  return lista.map(x =>
    `<option value="${e(x.descripcion)}"${x.descripcion === elegida ? " selected" : ""}>${e(x.descripcion)}</option>`
  ).join("");
}

/* ---------- Fuera de la red (candidatos del DENUE) ---------- */
export function opcionesEntidadFuera(v) {
  return `<option value="">Selecciona un estado</option>`
    + opcionesCatalogoTexto(v.fueraEntidades, v.fueraForm.codEnt);
}

export function opcionesMunicipioFuera(v) {
  if (!v.fueraForm.codEnt) return `<option value="">Elige un estado primero</option>`;
  if (!v.fueraMunicipios.length) return `<option value="">Cargando…</option>`;
  // Sin municipio = toda la entidad: útil cuando en el municipio no hay nada.
  return `<option value="">Todo el estado</option>`
    + opcionesCatalogoTexto(v.fueraMunicipios, v.fueraForm.codMun);
}

export function fueraResultadosCuerpo(v) {
  if (v.fueraBuscando) return `<div class="spinner-row">Consultando el directorio del INEGI…</div>`;
  if (v.fueraError) {
    return `
      <div class="dp-vacio">
        <p class="dp-vacio-titulo">No se pudo completar la búsqueda</p>
        <p class="dp-texto">${e(v.fueraError)}</p>
      </div>`;
  }
  if (!v.fueraBuscado) {
    return `
      <div class="dp-vacio">
        <p class="dp-vacio-titulo">Elige estado y especialidad</p>
        <p class="dp-texto">Se consultará el Directorio Estadístico Nacional de Unidades Económicas (DENUE) del INEGI, que es información pública de establecimientos.</p>
      </div>`;
  }
  if (!v.fueraCandidatos.length) {
    return `
      <div class="dp-vacio">
        <p class="dp-vacio-titulo">Sin consultorios para esa búsqueda</p>
        <p class="dp-texto">El INEGI no reporta ${e(v.fueraTipo || "consultorios")} en el área ${e(v.fueraArea)}. Prueba con el municipio "Todo el estado".</p>
      </div>`;
  }
  return `
    <div class="dp-aviso-candidatos">
      <span class="badge pendiente">Fuera de la red</span>
      <p class="dp-texto">
        ${e(String(v.fueraCandidatos.length))} establecimiento(s) según ${e(v.fueraFuente)} · área ${e(v.fueraArea)}.
        <b>No son proveedores del portal:</b> no tienen clave, no se les puede agendar y sus datos no se guardan.
        El INEGI registra el establecimiento, no al médico -- por eso no trae cédula, costo ni convenio.
      </p>
      ${v.fueraTipo ? `<p class="dp-texto dp-aviso-alcance">
        <b>Se buscaron ${e(v.fueraTipo)}.</b> El INEGI no clasifica por especialidad médica:
        cardiología, pediatría, dermatología y las demás comparten el mismo giro, así que
        <b>hay que confirmar la especialidad al contactarlos</b>. Los que mencionan el término
        buscado en su nombre aparecen primero.
      </p>` : ""}
    </div>
    <div class="table-wrap">
      <table class="mini-table">
        <thead>
          <tr><th>Establecimiento</th><th>Giro registrado</th><th>Domicilio</th><th>Contacto</th></tr>
        </thead>
        <tbody>
          ${v.fueraCandidatos.map(c => `
            <tr>
              <td data-label="Establecimiento">
                <div class="dp-fuerte">${e(c.nombre || "Sin nombre registrado")}</div>
                ${c.razon_social ? `<div class="dp-muted">${e(c.razon_social)}</div>` : ""}
              </td>
              <td data-label="Giro registrado">${e(c.especialidad || "—")}</td>
              <td data-label="Domicilio">
                <div>${e(c.calle_num_ext_int || "—")}</div>
                <div class="dp-muted">${e([c.colonia, c.codigo_postal ? "C.P. " + c.codigo_postal : "", c.ubicacion].filter(Boolean).join(" · "))}</div>
              </td>
              <td data-label="Contacto">
                <div>${e(c.telefono || "Sin teléfono")}</div>
                ${c.email ? `<div class="dp-muted">${e(c.email)}</div>` : ""}
              </td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

export function pantallaFueraDeRed(v) {
  return `
    ${encabezado({
      volver: "← Volver al directorio", accionVolver: "ir-inicio",
      titulo: "Buscar fuera de la red",
      texto: "Consultorios que el INEGI reporta en una zona, como candidatos a contratar cuando la red no tiene cobertura. Es información pública de establecimientos: para incorporar a alguien hay que darlo de alta y validar su cédula profesional.",
      // El alcance real (tipo de consultorio, no especialidad) se explica en
      // el campo de búsqueda y en el aviso de resultados.
    })}
    <div class="card tono-azul">
      <div class="card-body">
        <div class="dp-grid-campos">
          <div class="field dp-campo">
            <label for="dp-fr-estado">Estado</label>
            <select id="dp-fr-estado" data-campo-fuera="codEnt">${opcionesEntidadFuera(v)}</select>
          </div>
          <div class="field dp-campo">
            <label for="dp-fr-mun">Municipio</label>
            <select id="dp-fr-mun" data-campo-fuera="codMun">${opcionesMunicipioFuera(v)}</select>
          </div>
        </div>
        <div class="dp-grid-campos">
          <div class="field dp-campo">
            <label for="dp-fr-esp">Especialidad o término de búsqueda</label>
            <input type="text" id="dp-fr-esp" data-campo-fuera="especialidad" placeholder="cardiología" value="${e(v.fueraForm.especialidad)}" autocomplete="off">
            <span class="dp-nota">El INEGI agrupa por tipo de consultorio, no por especialidad: las especialidades médicas devuelven "consultorios de medicina especializada". Odontología, psicología, nutrición, optometría y terapia sí tienen giro propio.</span>
          </div>
        </div>
        <div class="dp-acciones dp-enviar">
          <button class="btn btn-primary" data-accion="buscar-fuera-de-red"${v.fueraPuedeBuscar && !v.fueraBuscando ? "" : " disabled"}>Buscar</button>
          <span class="dp-nota">${e(v.fueraPuedeBuscar ? "Listo para buscar." : "Elige un estado y escribe al menos 3 caracteres de la especialidad.")}</span>
        </div>
      </div>
    </div>
    <div class="card tono-verdeazul" id="dp-fuera-resultados">${fueraResultadosCuerpo(v)}</div>`;
}

export function pantallaAlta(v) {
  // La misma pantalla captura un alta nueva y corrige una en revisión
  // (botón "Editar" de Solicitudes, solo Administrador).
  const cabecera = v.editando
    ? encabezado({
        volver: "← Volver a solicitudes", accionVolver: "ir-solicitudes",
        titulo: "Editar solicitud " + v.editandoFolio,
        texto: "Corrige los datos antes de aprobarla o rechazarla. Al guardar, la solicitud sigue en revisión.",
      })
    : encabezado({
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
              <select id="dp-esp" data-campo="specialty">
                <option value="">Selecciona una especialidad</option>
                ${opcionesEspecialidadAlta(f.specialty)}
              </select>
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
              <select id="dp-estado-sel" data-campo="estado">
                <option value="">Selecciona un estado</option>
                ${opcionesEntidadAlta(v)}
              </select>
            </div>
            <div class="field dp-campo">
              <label for="dp-mun-sel">Municipio</label>
              <select id="dp-mun-sel" data-campo="municipio">${opcionesMunicipio(v)}</select>
            </div>
          </div>
          <h3 class="dp-subtitulo dp-subtitulo-espacio">Domicilio donde da la consulta</h3>
          ${campo("dp-calle", "calleNumExtInt", "Calle, No. Ext. y No. Int.", "Av. Vallarta 1450, Int. 302")}
          <div class="dp-grid-campos">
            ${campo("dp-colonia", "colonia", "Colonia", "Americana")}
            ${campo("dp-cp", "codigoPostal", "Código Postal", "44100")}
          </div>
          <div class="dp-grid-campos">
            ${campo("dp-tel", "phone", "Teléfono", "33 1234 5678")}
            ${campo("dp-mail", "email", "Correo electrónico", "consultorio@correo.mx")}
          </div>
          <div class="dp-acciones dp-enviar">
            <button class="btn btn-primary" data-accion="enviar-alta">${v.editando ? "Guardar cambios" : "Enviar solicitud de alta"}</button>
            ${v.editando ? `<button class="btn btn-secondary" data-accion="cancelar-edicion">Cancelar</button>` : ""}
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
    <span class="badge ${clasePorOrigen(v.detailOrigen)}">${e(v.detailSource)}</span>
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
        <p class="dp-texto">Folio ${e(v.bookingFolio)} · ${e(v.detailClinic)}</p>
        <p class="dp-texto">${e(v.detailDomicilioCalle)}, ${e(v.detailDomicilioResto)}.</p>
      </div>`;
  }
  const dato = (titulo, valor) => `<div><dt>${e(titulo)}</dt><dd>${e(valor)}</dd></div>`;
  return `
    ${cabecera}
    <dl class="dp-ficha-datos">
      ${dato("Clave del proveedor", v.detailClave)}
      ${dato("Consultorio", v.detailClinic)}
      ${dato("Domicilio de consulta", v.detailDomicilioCalle)}
      ${dato("Colonia, C.P. y zona", v.detailDomicilioResto)}
      ${dato("Horario", v.detailSchedule)}
      ${dato("Consulta", v.detailPrice)}
      ${dato("Convenios", v.detailConvenio)}
      ${dato("Teléfono", v.detailPhone)}
    </dl>`;
}

export function fichaPie(v) {
  if (v.bookingPick) {
    return `
      <button class="btn btn-primary" data-accion="confirmar-cita"${v.bookingGuardando ? " disabled" : ""}>Confirmar cita</button>
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
