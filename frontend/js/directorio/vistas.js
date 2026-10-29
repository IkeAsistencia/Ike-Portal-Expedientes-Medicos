/* Directorio de Proveedores (maqueta): cálculo de lo que se pinta y
   plantillas HTML de cada sub-pantalla.

   calcular(estado) es el equivalente de renderVals() del prototipo
   original: a partir del estado arma todos los textos y listas (mismas
   fórmulas, mismos textos). Las plantillas solo acomodan esos valores con
   el diseño del portal (tarjetas, botones, tablas, badges). Todo texto
   pasa por escapeHtml; los clics se resuelven por delegación con
   data-accion (ver pantallas/directorio-proveedores.js). */
import { escapeHtml as e, normalizarTexto } from "../core/formato.js";
import { esPerfilAdministrador, rfcActual } from "../core/sesion.js";
import {
  URL_VALIDAR_RFC_SAT, URL_CONSULTAR_CEDULA_SEP, DOCUMENTOS_ALTA,
  revisarRfc, normalizarRfc, etiquetaTipoRfc, cedulaConFormatoValido, revisarFormularioAlta,
  DIAS_SEMANA, serializarHorario, COSTOS_APROXIMADOS, leerCosto,
} from "./validacion-alta.js";
import { coordinacionActual } from "../core/coordinar-cita.js";

/* Estatus en los que una solicitud de alta todavía se puede corregir --
   mismo criterio que ESTATUS_EDITABLES en
   app/repositories/solicitudes_alta_medico_repo.py (el backend lo exige
   igual: editar una ya resuelta responde 409). */
const ESTATUS_EDITABLES = ["En revisión"];
import { ICONOS } from "../componentes/iconos.js";
import {
  PRICE_OPTIONS,
  raw, visible, valoresUnicosCatalogo, zonasDelPadron, resumenDelPadron,
  entidadesAltaCache, entidadesAltaFallaron, municipiosAltaCache, municipiosAltaCargados,
  especialidadesKpiCache, todasLasEspecialidades,
  ETIQUETA_DENTRO_DE_LA_RED, ETIQUETA_RED_DE_APOYO, ETIQUETA_FUERA_DE_LA_RED,
} from "./datos.js";

/* Opciones del filtro "Tipo de proveedor" (chips de filtrosResultados), en
   el mismo orden que se ven en el padrón: catálogo, apoyo, portal. */
const ORIGEN_OPTIONS = [
  { valor: "catalogo", texto: ETIQUETA_DENTRO_DE_LA_RED },
  { valor: "apoyo", texto: ETIQUETA_RED_DE_APOYO },
  { valor: "portal", texto: ETIQUETA_FUERA_DE_LA_RED },
];

/* Fechas locales (no UTC: a la medianoche toISOString() ya diría "mañana"). */
const DIAS_CITA_MAXIMO = 365;   // igual que DIAS_CITA_MAXIMO en agenda_proveedores_service.py
const NOMBRES_DIA = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
const dos = (n) => String(n).padStart(2, "0");

function fechaLocalISO(d) {
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`;
}

/* "2026-10-22" -> { dow: "Jue", num: "22", completa: "Jue 22/10/2026" } */
function etiquetaDeFecha(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  const dia = new Date(a, m - 1, d);
  return { dow: NOMBRES_DIA[dia.getDay()], num: String(d), completa: `${NOMBRES_DIA[dia.getDay()]} ${dos(d)}/${dos(m)}/${a}` };
}

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
  // Sin acentos de los dos lados: el padrón los guarda como el sistema
  // central ("MERIDA") y quien busca escribe "Mér...".
  const q = normalizarTexto(s.query);
  const sugg = [];
  if (q.length >= 2 && s.screen === "home") {
    const coincide = (valor) => normalizarTexto(valor).includes(q);
    valoresUnicosCatalogo("municipio").forEach(m => { if (coincide(m)) sugg.push({ label: m, kind: "Municipio", term: m }); });
    valoresUnicosCatalogo("estado").forEach(es => { if (coincide(es)) sugg.push({ label: es, kind: "Estado", term: es }); });
    valoresUnicosCatalogo("specialty").forEach(sp => { if (coincide(sp)) sugg.push({ label: sp, kind: "Especialidad", term: sp }); });
    valoresUnicosCatalogo("name").forEach(n => { if (coincide(n)) sugg.push({ label: n, kind: "Médico", term: n }); });
  }
  return sugg.slice(0, 6);
}

/* El KPI que lleva cada tarjeta de especialidad: cuántos proveedores del
   padrón hay dentro de la red (hoja "Padrón de proveedores", con convenio),
   cuántos en la red de apoyo (hoja "Proveedores red de apoyo", también con
   convenio pero identificada aparte) y cuántos están fuera de la red
   (aprobados en el portal, sin ese proceso formal todavía). El servidor los
   manda como dentro_de_red / red_de_apoyo / fuera_de_red. Los conteos son
   reales -- salen de amarrar cada proveedor a una especialidad del catálogo,
   ver app/repositories/especialidades_repo.py.

   Una especialidad en 0 no se esconde: se marca "Sin proveedores" y se deja
   clickeable, porque justo esa es la que hay que salir a contratar (ahí
   entra "Buscar fuera de la red"). */
function kpiEspecialidad(x) {
  const dentro = Number(x.dentro_de_red) || 0;
  const apoyo = Number(x.red_de_apoyo) || 0;
  const fuera = Number(x.fuera_de_red) || 0;
  if (dentro + apoyo + fuera === 0) return "Sin proveedores";
  return dentro + " dentro de la red · " + apoyo + " red de apoyo · " + fuera + " fuera de la red";
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
    vacia: (Number(x.dentro_de_red) || 0) + (Number(x.red_de_apoyo) || 0) + (Number(x.fuera_de_red) || 0) === 0,
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
  // Estados y municipios DONDE HAY proveedores, sacados del padrón real
  // (ver zonasDelPadron en datos.js). Acotados a la especialidad elegida:
  // no tiene caso ofrecer una zona que no tiene a nadie de esa especialidad.
  const zonas = zonasDelPadron(s.specialtyId);
  const estadoObj = zonas.find(x => x.name === s.estado);
  const info = s.screen === "results" || s.screen === "compare" ? raw(s) : { list: [], label: "", sub: "" };
  const listed = s.screen === "results" ? visible(s) : [];
  const d = s.detail;
  const cedulaOk = cedulaConFormatoValido(s.form.cedula);
  const cedulaVacia = !(s.form.cedula || "").trim();
  const faltasAlta = revisarFormularioAlta(s.form);
  const rfcAlta = revisarRfc(s.form.rfc);
  const rfcMostrarError = !!s.altaIntento || normalizarRfc(s.form.rfc).length >= 12;
  const compareItems = visible(s).filter(x => s.compare.indexOf(x.id) >= 0);
  const esAdministrador = esPerfilAdministrador();

  // Cobertura por estado: conteo real del padrón, no una cifra generada.
  const zonasTodas = zonasDelPadron();
  const coverageRaw = zonasTodas.map(x => ({ name: x.name, total: x.total }));
  const maxCov = Math.max(1, ...coverageRaw.map(c => c.total));
  const municipiosCubiertos = zonasTodas.reduce((a, x) => a + x.municipios.length, 0);
  const {
    total: totalPadron, dentroDeRed, redDeApoyo, fueraDeRed, especialidadesConProveedor,
  } = resumenDelPadron();
  // Catálogo real de especialidades, ya partido por el servidor en lo que
  // cabe en pantalla (16 = 4 renglones de 4) y lo que va al combo.
  const catalogoEsp = especialidadesKpiCache();
  const specTotals = todasLasEspecialidades().map(x => ({
    name: x.descripcion,
    total: (Number(x.dentro_de_red) || 0) + (Number(x.red_de_apoyo) || 0) + (Number(x.fuera_de_red) || 0),
  }));
  const pending = s.requests.filter(r => r.status === "En revisión").length;

  // Agenda: los días y horarios REALMENTE libres los manda el servidor (ver
  // cargarAgenda en datos.js) -- s.agenda llega vacío mientras se consulta.
  // Además de los 7 días y horarios sugeridos, la cita se puede capturar en
  // CUALQUIER fecha y hora (el médico suele aceptar por teléfono una hora que
  // no está en la lista, ej. 12:45): bookingFechaLibre y bookingHoraLibre.
  const bookingDayIndex = s.bookingDay == null ? 0 : s.bookingDay;
  const fechaLibre = s.bookingFechaLibre || "";
  const days = (s.agenda || []).map((dia, i) => ({
    indice: i,
    dow: dia.dia_semana, num: String(dia.dia_mes), fecha: dia.fecha,
    slots: dia.atiende === false ? "No atiende" : dia.horarios.length ? dia.horarios.length + " horarios" : "sin cupo",
    // Un día sin horarios sugeridos libres se puede elegir igual (se captura la
    // hora a mano), salvo que el médico no atienda ese día.
    disabled: dia.atiende === false,
    elegido: !fechaLibre && i === bookingDayIndex,
  }));
  const diaElegido = fechaLibre ? s.agendaLibre : (s.agenda || [])[bookingDayIndex];
  const diaSinAtencion = !!diaElegido && diaElegido.atiende === false;

  // Para qué expediente es la cita (toda cita es para uno).
  const ctxCita = coordinacionActual();
  const textoComparable = (t) => normalizarTexto(String(t || "")).toUpperCase().trim();
  const mismaEspecialidad = (exp) => !!d && !!textoComparable(exp.especialidad)
    && textoComparable(exp.especialidad) === textoComparable(d.specialty);
  const busquedaExp = textoComparable(s.expedienteBusqueda);
  const avisosCita = [];
  if (ctxCita && d) {
    if (textoComparable(ctxCita.especialidad) && !mismaEspecialidad(ctxCita)) {
      avisosCita.push(`El expediente pide ${ctxCita.especialidad} y este médico es ${d.specialty}.`);
    }
    const zonaExp = [ctxCita.municipio, ctxCita.entidad].filter(Boolean);
    const zonaMed = [d.municipio, d.estado].filter(Boolean);
    if (zonaExp.length && zonaMed.length && zonaExp.map(textoComparable).join("|") !== zonaMed.map(textoComparable).join("|")) {
      avisosCita.push(`El expediente es de ${zonaExp.join(", ")} y el consultorio está en ${zonaMed.join(", ")}.`);
    }
  }
  const horaEfectiva = s.bookingHoraLibre || s.bookingSlot || "";
  const daySlots = (diaElegido ? diaElegido.horarios : []).map(sl => ({
    label: sl, elegido: !s.bookingHoraLibre && sl === s.bookingSlot,
  }));
  const selDay = fechaLibre ? etiquetaDeFecha(fechaLibre) : days[bookingDayIndex];
  const hoy = new Date();
  const limite = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + DIAS_CITA_MAXIMO);

  return {
    screen: s.screen,
    breadcrumb: { home: "Inicio", register: "Inicio / Alta de médico", admin: "Inicio / Solicitudes", metrics: "Inicio / Métricas", compare: "Inicio / Comparar" }[s.screen]
      || (s.screen === "zone" ? "Inicio / " + s.specialty : "Inicio / " + (s.searchTerm ? "Búsqueda" : s.specialty + " / " + s.municipio)),
    pendingBadge: pending ? "(" + pending + ")" : "",

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

    // Coordinar cita desde un expediente (botón de Seguimiento): lo que se
    // muestra en el aviso de arriba; null cuando no se viene de un expediente.
    coord: (() => {
      const c = coordinacionActual();
      if (!c) return null;
      return {
        expediente: c.expediente, paciente: c.paciente || "NA", especialidad: c.especialidad || "NA",
        entidad: c.entidad || "NA", municipio: c.municipio || "NA",
        nota: s.coordNota || "", fuera: !!s.coordFuera,
        desdeDirectorio: c.origen === "directorio",
      };
    })(),

    // Zona -- estados y municipios con proveedores de verdad. Vacío cuando
    // el padrón todavía no se ha cargado.
    specialty: s.specialty,
    estados: zonas.map(x => ({
      name: x.name,
      count: x.municipios.length + (x.municipios.length === 1 ? " municipio" : " municipios"),
      elegido: x.name === s.estado,
    })),
    hayZonas: zonas.length > 0,
    hasEstado: !!estadoObj,
    municipios: (estadoObj ? estadoObj.municipios : []).map(m => ({
      name: m.name,
      meta: m.total + (m.total === 1 ? " especialista" : " especialistas"),
    })),

    // Resultados
    priceOptions: PRICE_OPTIONS.map(p => ({ label: p.label, max: p.max, elegido: f.maxPrice === p.max })),
    origenOptions: ORIGEN_OPTIONS.map(o => ({ ...o, elegido: (f.origenes || []).includes(o.valor) })),
    fTele: f.tele, fSeguro: f.seguro, orden: f.orden,
    filterSummary: [
      f.maxPrice < 9999 ? "≤ $" + f.maxPrice : null,
      f.tele ? "teleconsulta" : null,
      f.seguro ? "con convenio" : null,
      ...(f.origenes || []).map(o => ORIGEN_OPTIONS.find(x => x.valor === o)?.texto).filter(Boolean),
    ].filter(Boolean).join(" · ") || "Sin filtros activos",
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
      // El horario que trae el padrón; la disponibilidad real sale de la
      // agenda, al abrir la ficha.
      availability: x.schedule,
      price: x.price, source: x.source,
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
      { label: "Horario", key: "schedule" }, { label: "Convenios", key: "convenio" },
      { label: "Teléfono", key: "phone" }, { label: "Cobertura", key: "source" }
    ].map(r => ({ label: r.label, cells: compareItems.map(x => String(x[r.key] || "—")) })),

    // Ficha / agenda
    hasDetail: !!d,
    detailName: d ? d.name : "", detailSpecialty: d ? d.specialty : "", detailCedula: d ? d.cedula : "",
    detailClinic: d ? d.clinic : "", detailSchedule: d ? d.schedule : "",
    detailDomicilioCalle: d ? (d.calleNumExtInt || "Domicilio no especificado") : "",
    detailDomicilioResto: d ? _domicilioResto(d) : "",
    detailPrice: d ? d.price : "", detailPhone: d ? d.phone : "", detailSource: d ? d.source : "", detailConvenio: d ? d.convenio : "",
    detailClave: d ? d.clave : "", detailOrigen: d ? d.origen : "",
    bookingIdle: s.bookingStep === "idle", bookingPick: s.bookingStep === "pick", bookingDone: s.bookingStep === "done",
    bookingExpediente: s.bookingStep === "expediente",    // Paso "¿Para qué expediente?": los que coinciden con la especialidad del
    // médico van primero.
    expedientesCita: s.expedientesCita === null ? null : s.expedientesCita
      .filter(x => !busquedaExp || String(x.expediente).includes(busquedaExp) || textoComparable(x.nombre_paciente).includes(busquedaExp))
      .map(x => ({
        cl: x.expediente, paciente: x.nombre_paciente || "Sin nombre", especialidad: x.especialidad || "NA",
        zona: [x.municipio, x.entidad].filter(Boolean).join(", ") || "Sin zona",
        estatus: x.estatus, cuenta: x.cuenta || "", coincide: mismaEspecialidad(x),
      }))
      .sort((a, b) => (b.coincide - a.coincide) || (b.cl - a.cl)),
    expedientesTotal: (s.expedientesCita || []).length,
    expedienteBusqueda: s.expedienteBusqueda || "",
    citaExpediente: ctxCita ? {
      cl: ctxCita.expediente, paciente: ctxCita.paciente || "NA",
      especialidad: ctxCita.especialidad || "NA",
      zona: [ctxCita.municipio, ctxCita.entidad].filter(Boolean).join(", ") || "NA",
      puedeCambiar: ctxCita.origen === "directorio",
    } : null,
    citaAvisos: avisosCita,
    diaSinAtencion,
    bookingDays: days, bookingSlots: daySlots,
    bookingNote: s.bookingGuardando
      ? "Agendando…"
      : horaEfectiva && selDay
        ? "Cita: " + (selDay.completa || selDay.dow + " " + selDay.num) + " a las " + horaEfectiva
        : "Elige un horario para confirmar.",
    bookingSummary: (selDay ? (selDay.completa || selDay.dow + " " + selDay.num) : "") + " · " + horaEfectiva,
    bookingFechaLibre: fechaLibre, bookingHoraLibre: s.bookingHoraLibre || "",
    bookingFechaMin: fechaLocalISO(hoy), bookingFechaMax: fechaLocalISO(limite),
    bookingFolio: s.bookingFolio || "",
    bookingGuardando: !!s.bookingGuardando,

    // Métricas -- todas del padrón real (antes "Especialistas activos" y
    // "Zonas cubiertas" salían de una cifra generada, y había un KPI de
    // "Importados de Google" que nunca importó nada).
    kpis: [
      { label: "Proveedores en el padrón", value: String(totalPadron), note: dentroDeRed + " dentro de la red · " + redDeApoyo + " red de apoyo · " + fueraDeRed + " fuera de la red", icono: "personas", clase: "kpi-total" },
      { label: "Municipios con cobertura", value: String(municipiosCubiertos), note: coverageRaw.length + (coverageRaw.length === 1 ? " estado" : " estados"), icono: "ubicacion", clase: "kpi-cita" },
      { label: "Solicitudes en revisión", value: String(pending), note: s.requests.length + " solicitudes totales", icono: "expediente", clase: "kpi-proceso" },
      { label: "Especialidades con proveedor", value: String(especialidadesConProveedor) + " de " + (catalogoEsp.total || 0), note: "Del catálogo de especialidades", icono: "expediente", clase: "kpi-seguimiento" }
    ],
    coverage: coverageRaw.map(c => ({ name: c.name, value: c.total + (c.total === 1 ? " especialista" : " especialistas"), width: Math.round(c.total / maxCov * 100) })),
    hayCobertura: coverageRaw.length > 0,
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
      consultorio: r.consultorio, horario: r.horario,
      costo: r.costo ? leerCosto(r.costo).texto : "",
      // Cédula y RFC tal como se capturaron. Antes se les ponía una ✓ como si
      // estuvieran verificados; solo se revisó el formato, así que la
      // confirmación la hace quien revisa con los botones de la SEP y el SAT.
      cedula: r.cedula || "—",
      rfc: r.rfc || "Sin RFC",
      rfcTipo: etiquetaTipoRfc(r.rfcRevision.tipo),
      // Avisos y botones de verificación: solo para quien revisa (Administrador).
      rfcAviso: !esAdministrador || !r.rfc ? "" : !r.rfcRevision.formato_valido ? "Formato inválido"
        : !r.rfcRevision.digito_correcto ? "Dígito verificador no cuadra" : "",
      mostrarVerificacion: esAdministrador,
      documentos: DOCUMENTOS_ALTA.map(d => ({
        tipo: d.tipo, corta: d.corta,
        subido: !!r.documentos[d.tipo],
        nombre: r.documentos[d.tipo] ? r.documentos[d.tipo].nombre_archivo : "",
      })),
      // El contenido lo ve solo el Administrador o quien capturó (lo exige
      // también el servidor); los demás solo ven si se subió.
      puedeVerDocumentos: esAdministrador || (!!r.rfcSolicito && r.rfcSolicito === rfcActual()),
      status: r.status,
      // La clave que le tocó al aprobarse: es con la que ya se le pueden
      // agendar citas, y la conserva aunque después llegue en la carga.
      claveProveedor: r.claveProveedor || "—",
      // Revisar una solicitud (aprobar, rechazar o corregirla antes) es
      // exclusivo de Administrador; el backend lo exige igual, esto solo
      // evita mostrar botones que iban a responder 403.
      puedeResolver: esAdministrador,
      // Editar solo mientras nadie la haya resuelto (en revisión). Ya
      // aprobada, el proveedor existe en el padrón con su clave y puede
      // tener citas (ver ESTATUS_EDITABLES en el repositorio).
      puedeEditar: esAdministrador && ESTATUS_EDITABLES.includes(r.status),
      statusClass: r.status === "Aprobada" ? "activo" : r.status === "Rechazada" ? "inactivo" : "pendiente",
    })),

    // Alta de médico (la misma pantalla sirve para capturar un alta nueva y
    // para corregir una solicitud en revisión -- ver editandoFolio).
    registered: !!s.registered,
    regName: s.registered ? s.registered.name : "", regFolio: s.registered ? s.registered.folio : "",
    editando: !!s.editandoFolio,
    editandoFolio: s.editandoFolio || "",
    form: s.form,
    formEntidades: entidadesAltaCache(),
    formEntidadesFallaron: entidadesAltaFallaron(),
    formMunicipios: municipiosAltaCache(s.form.estado),
    formMunicipiosCargados: municipiosAltaCargados(s.form.estado),

    // Búsqueda fuera de la red (Google Maps). Usa los catálogos REALES de
    // Entidad y Municipio (los mismos del Alta de médico), no el catálogo de
    // la pantalla Zona -- ver app/services/google_maps_service.py.
    fueraForm: s.fueraForm,
    fueraEntidades: entidadesAltaCache(),
    fueraEntidadesFallaron: entidadesAltaFallaron(),
    fueraMunicipios: municipiosAltaCache(s.fueraForm.codEnt),
    fueraMunicipiosCargados: municipiosAltaCargados(s.fueraForm.codEnt),
    fueraEspecialidades: todasLasEspecialidades().map(x => x.descripcion).sort((a, b) => a.localeCompare(b, "es")),
    fueraBuscando: !!s.fueraBuscando,
    fueraError: s.fueraError || "",
    fueraBuscado: !!s.fueraResultados,
    fueraArea: s.fueraResultados ? s.fueraResultados.area : "",
    fueraFuente: s.fueraResultados ? s.fueraResultados.fuente : "",
    fueraConsulta: s.fueraResultados ? (s.fueraResultados.consulta || "") : "",
    fueraCandidatos: s.fueraResultados ? s.fueraResultados.candidatos : [],
    fueraTipo: s.fueraResultados ? (s.fueraResultados.tipo_descripcion || "") : "",
    // Vista de los resultados: "mapa" (default) o "lista". El mapa es lo que
    // pidió el usuario para decidir a quién contactar por zona.
    fueraVista: s.fueraVista || "mapa",
    // ¿Se puede dibujar el mapa? Necesita la llave del navegador
    // (GOOGLE_MAPS_BROWSER_API_KEY, ver app/config.py). Sin llave se oculta
    // la opción Mapa en vez de mostrar un mapa vacío.
    fueraPuedeMapa: !!s.mapaGoogleListo,
    fueraPuedeBuscar: !!(s.fueraForm.codEnt && s.fueraForm.especialidad),
    // Cédula profesional: solo se revisa el formato (7 u 8 dígitos), mientras
    // se escribe y sin botón. Igual que el RFC, el error espera a que se
    // intente enviar para no marcarlo a la primera tecla.
    cedulaValor: (s.form.cedula || "").trim(),
    cedulaMensaje: cedulaVacia ? "Opcional: 7 u 8 dígitos."
      : cedulaOk ? "Formato correcto."
      : s.altaIntento ? "La cédula debe tener 7 u 8 dígitos." : "7 u 8 dígitos.",
    cedulaClase: cedulaVacia ? "dp-neutro" : cedulaOk ? "dp-ok" : s.altaIntento ? "dp-error" : "dp-neutro",
    submitNote: faltasAlta.length
      ? (s.altaIntento ? `Faltan por completar o corregir: ${faltasAlta.map(f => f.etiqueta).join(", ")}.` : "Completa todos los datos para enviar.")
      : (s.editandoFolio ? "Puedes guardar los cambios." : "Puedes enviar la solicitud."),

    // RFC del alta (opcional). El error se muestra hasta que ya tiene el
    // largo de un RFC o se intentó enviar: no a la primera letra. Vacío nunca
    // es error.
    rfcValor: normalizarRfc(s.form.rfc),
    rfcTipo: rfcAlta.estado === "valido" ? etiquetaTipoRfc(rfcAlta.tipo) : "",
    horarioResumen: serializarHorario(s.form.horarioBloques) || "Elige los días y las horas de atención.",

    // La advertencia del dígito verificador es para quien revisa
    // (Administrador): a quien captura solo se le dice si el formato es válido.
    rfcMensaje: rfcAlta.estado === "vacio" || !rfcMostrarError ? "Opcional: 13 caracteres (persona física) o 12 (persona moral)."
      : rfcAlta.estado === "valido" && !esAdministrador ? "Formato correcto." : rfcAlta.mensaje,
    rfcClase: rfcAlta.estado === "vacio" || !rfcMostrarError ? "dp-neutro"
      : rfcAlta.estado !== "valido" ? "dp-error"
      : rfcAlta.digitoCorrecto || !esAdministrador ? "dp-ok" : "dp-advertencia",
    // Botones del SAT y la SEP e indicaciones de revisión: solo Administrador.
    mostrarVerificacion: esAdministrador,
    // Del directorio, el Administrador solo usa Solicitudes, Alta y Métricas.
    soloAdministracion: esAdministrador,

    // Documentos opcionales: el archivo elegido (se sube al guardar) y, al
    // editar, el que la solicitud ya tiene.
    documentosAlta: DOCUMENTOS_ALTA.map(d => {
      const archivo = s.archivosAlta[d.tipo];
      const guardado = s.editandoFolio ? s.documentosEditando[d.tipo] : null;
      return {
        ...d,
        archivoNombre: archivo ? archivo.name : "",
        archivoTamano: archivo ? tamanoLegible(archivo.size) : "",
        guardadoNombre: guardado ? guardado.nombre_archivo : "",
      };
    }),
    regDocumentos: s.registered && s.registered.documentos ? s.registered.documentos : [],

    footerCount: "Fuente: padrón del portal",
  };
}

/* ---------- Piezas comunes ---------- */
function tamanoLegible(bytes) {
  return bytes >= 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";
}

/* "Verificar en el SAT / en la SEP": enlace normal al sitio oficial que,
   además, copia el dato al hacer clic (ver copiarParaVerificar en la
   pantalla). Esos sitios tienen captcha: no se les puede mandar ya capturado. */
function enlaceVerificar(url, valor, que, texto) {
  return `<a class="dp-verificar-externo" href="${e(url)}" target="_blank" rel="noopener noreferrer"
    data-copiar="${e(valor || "")}" data-que="${e(que)}"
    title="Copia el ${e(que)} y abre el sitio oficial en otra pestaña">${e(texto)} ↗</a>`;
}
/* Color del distintivo según de dónde salió el proveedor: "Dentro de la red"
   (hoja "Padrón de proveedores" del Excel oficial, con convenio) en verde,
   "Red de apoyo" (hoja "Proveedores red de apoyo", también con convenio
   pero identificada aparte) en morado, "Fuera de la red" (aprobado en el
   portal, sin ese proceso formal todavía) en ámbar, para que se note de un
   vistazo cuál tiene convenio y de qué hoja viene. */
const clasePorOrigen = (origen) => (
  origen === "portal" ? "pendiente" : origen === "apoyo" ? "programado" : "seguimiento"
);

/* "Volver": al directorio para el Proveedor; a Solicitudes para el
   Administrador, que no tiene la búsqueda del directorio. */
const volverSegunPerfil = (v) => v.soloAdministracion
  ? { volver: "← Volver a solicitudes", accionVolver: "ir-solicitudes" }
  : { volver: "← Volver al directorio", accionVolver: "ir-inicio" };

function encabezado({ volver, accionVolver, titulo, texto, extra = "", idTexto = "" }) {
  return `
    <div class="dp-encabezado${extra ? " dp-encabezado-acciones" : ""}">
      <div class="dp-encabezado-texto">
        ${volver ? `<button class="btn dp-btn-ghost dp-volver" data-accion="${accionVolver}">${e(volver)}</button>` : ""}
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

/* Aviso fijo mientras se coordina una cita desde un expediente: de cuál viene,
   en qué punto se detuvo la búsqueda y por qué, y cómo volver sin agendar. */
export function avisoCoordinacion(v) {
  const c = v.coord;
  if (!c) return "";
  return `
    <div class="dp-aviso-cita">
      <div class="dp-aviso-cita-texto">
        <strong>Coordinando cita para el expediente ${e(c.expediente)}</strong>
        <span>Paciente: ${e(c.paciente)} · Especialidad: ${e(c.especialidad)} · ${e(c.municipio)}, ${e(c.entidad)}</span>
        ${c.nota ? `<span class="dp-aviso-cita-nota">${e(c.nota)}</span>` : ""}
      </div>
      <div class="dp-acciones">
        ${c.fuera ? `<button class="btn btn-secondary" data-accion="ir-fuera-de-red">Buscar fuera de la red</button>` : ""}
        <button class="btn btn-secondary" data-accion="cancelar-coordinacion">${c.desdeDirectorio ? "Quitar expediente" : "Cancelar y volver al expediente"}</button>
      </div>
    </div>`;
}

export function pie(v) {
  return `
    <span>Padrón, altas, citas y métricas reales.</span>
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
          : `<div class="dp-grid-especialidades">
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

  // Sin zonas = no hay proveedores de esa especialidad en el padrón. Antes
  // siempre salían seis estados fijos aunque no hubiera nadie en ellos.
  if (!v.hayZonas) {
    return `
      ${encabezado({
        volver: "← Todas las especialidades", accionVolver: "ir-inicio",
        titulo: v.specialty, texto: "Zonas donde el padrón tiene especialistas de esta especialidad.",
      })}
      <div class="card tono-ambar">
        <div class="dp-vacio">
          <p class="dp-vacio-titulo">Sin cobertura para ${e(v.specialty)}</p>
          <p class="dp-texto">El padrón no tiene proveedores de esta especialidad en ninguna zona todavía. Carga el catálogo de proveedores, da de alta un médico, o busca consultorios <b>fuera de la red</b> para evaluar su contratación.</p>
          <div class="dp-acciones">
            <button class="btn btn-primary" data-accion="ir-fuera-de-red">Buscar fuera de la red</button>
            <button class="btn btn-secondary" data-accion="ir-alta">Alta de médico</button>
          </div>
        </div>
      </div>`;
  }

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
// repintan sus partes (cabecera, filtros, conteo y lista).
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
          <div id="dp-res-lista"></div>
        </div>
      </div>
    </div>`;
}

// Sin selector Lista/Mapa: el padrón casi no trae coordenadas, así que el
// mapa de la zona salía vacío (se quitó, instrucción del usuario 2026-10-28).
// El mapa que sí funciona es el de "Buscar fuera de la red" (Google).
export function cabeceraResultados(v) {
  const acciones = `
    <div class="dp-acciones">
      <button class="btn btn-secondary" data-accion="ir-fuera-de-red">Buscar fuera de la red</button>
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
      <h2 class="dp-subtitulo">Tipo de proveedor</h2>
      <div class="dp-lista-opciones">
        ${v.origenOptions.map(o => `
          <button class="dp-opcion dp-opcion-compacta dp-opcion-origen-${o.valor}${o.elegido ? " dp-sel" : ""}" data-accion="origen" data-valor="${o.valor}">${e(o.texto)}</button>`).join("")}
      </div>
    </div>
    <div class="dp-seccion dp-seccion-linea">
      <h2 class="dp-subtitulo">Filtros</h2>
      ${casilla("tele", v.fTele, "Teleconsulta")}
      ${casilla("seguro", v.fSeguro, "Con convenio / seguro")}
    </div>
    <div class="field dp-campo dp-seccion-linea">
      <label for="dp-orden">Ordenar por</label>
      <select id="dp-orden">
        ${opcionOrden("nombre", "Nombre")}
        ${opcionOrden("precio", "Precio más bajo")}
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
          <span class="dp-origen-punto ${d.origen === "portal" ? "portal" : d.origen === "apoyo" ? "apoyo" : "catalogo"}" title="${e(d.source)}"></span>
          <span class="badge ${clasePorOrigen(d.origen)}">${e(d.source)}</span>
          <h3>${e(d.name)}</h3>
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
        <div class="dp-muted"><span class="dp-dato">${e(d.price)}</span></div>
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
      ...volverSegunPerfil(v),
      titulo: "Métricas del directorio", texto: "Cifras del padrón cargado en este portal: cobertura por estado y especialidades con oferta insuficiente.",
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
          ${v.hayCobertura
            ? v.coverage.map(c => `
            <div>
              <div class="dp-cobertura-fila">
                <span class="dp-fuerte">${e(c.name)}</span>
                <span class="dp-muted">${e(c.value)}</span>
              </div>
              <div class="dp-pista"><div class="dp-pista-valor" style="width:${Number(c.width)}%;"></div></div>
            </div>`).join("")
            : `<p class="dp-texto dp-muted">Todavía no hay proveedores con domicilio en el padrón. Carga el catálogo de proveedores para ver la cobertura.</p>`}
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
      // Para el Administrador es su pantalla de entrada: no hay a dónde volver.
      volver: v.soloAdministracion ? "" : "← Volver al directorio", accionVolver: "ir-inicio",
      titulo: "Solicitudes de alta",
      // Las indicaciones de revisión son para el Administrador; los demás
      // perfiles solo ven el estatus de sus solicitudes.
      texto: v.mostrarVerificacion
        ? "Antes de aprobar, confirma la cédula en la SEP y el RFC en el SAT con sus botones "
          + "(el dato se copia y el sitio oficial se abre en otra pestaña), y revisa los documentos que se hayan subido. "
          + "«Editar» solo aparece mientras la solicitud sigue en revisión."
        : "Estatus de las solicitudes de alta. Un Administrador las revisa y las aprueba o rechaza.",
      extra: `<span class="dp-nota">${e(v.adminSummary)}</span>`,
    })}
    <div class="card tono-verdeazul">
      <div class="table-wrap">
        <table class="mini-table dp-tabla-solicitudes">
          <thead>
            <tr>
              <th>Folio</th><th>Médico</th><th>Especialidad</th><th>Zona</th><th>Cédula prof.</th><th>RFC</th><th>Documentos</th><th>Clave</th><th>Estatus</th><th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${v.requests.map(r => `
              <tr>
                <td data-label="Folio" class="dp-tabular">${e(r.folio)}</td>
                <td data-label="Médico">
                  <div class="dp-fuerte">${e(r.name)}</div>
                  ${r.consultorio ? `<div class="dp-nota">${e(r.consultorio)}</div>` : ""}
                  ${r.horario ? `<div class="dp-nota">${e(r.horario)}</div>` : ""}
                  ${r.costo ? `<div class="dp-nota">${e(r.costo)}</div>` : ""}
                </td>
                <td data-label="Especialidad">${e(r.specialty)}</td>
                <td data-label="Zona">${e(r.zone)}</td>
                <td data-label="Cédula prof.">
                  <div class="dp-dato-verificar">
                    <span class="dp-tabular">${e(r.cedula)}</span>
                    ${r.mostrarVerificacion ? enlaceVerificar(URL_CONSULTAR_CEDULA_SEP, r.cedula === "—" ? "" : r.cedula, "cédula", "Verificar en la SEP") : ""}
                  </div>
                </td>
                <td data-label="RFC">
                  <div class="dp-dato-verificar">
                    <span class="dp-tabular">${e(r.rfc)}</span>
                    ${r.rfcTipo ? `<span class="dp-tipo-rfc">${e(r.rfcTipo)}</span>` : ""}
                    ${r.rfcAviso ? `<span class="dp-advertencia">${e(r.rfcAviso)}</span>` : ""}
                    ${r.mostrarVerificacion ? enlaceVerificar(URL_VALIDAR_RFC_SAT, r.rfc === "Sin RFC" ? "" : r.rfc, "RFC", "Verificar en el SAT") : ""}
                  </div>
                </td>
                <td data-label="Documentos">
                  <div class="dp-dato-verificar">
                    ${r.documentos.map(d => d.subido
                      ? (r.puedeVerDocumentos
                        ? `<button class="dp-doc-chip subido" data-accion="ver-documento" data-folio="${e(r.folio)}" data-tipo="${d.tipo}" title="Abrir ${e(d.nombre)}">✓ ${e(d.corta)} · Ver</button>`
                        : `<span class="dp-doc-chip subido">✓ ${e(d.corta)}</span>`)
                      : `<span class="dp-doc-chip">Sin ${e(d.corta.toLowerCase())}</span>`).join("")}
                  </div>
                </td>
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
    <span class="dp-subtitulo-chico">Cédula</span>
    <span class="dp-mensaje ${v.cedulaClase}">${e(v.cedulaMensaje)}</span>
    ${v.mostrarVerificacion ? enlaceVerificar(URL_CONSULTAR_CEDULA_SEP, v.cedulaValor, "cédula", "Verificar en la SEP") : ""}`;
}

/* Revisión del RFC mientras se escribe, con el tipo de persona que le
   corresponde por su largo (13 física, 12 moral). */
export function altaRfc(v) {
  return `
    <span class="dp-subtitulo-chico">RFC</span>
    ${v.rfcTipo ? `<span class="dp-tipo-rfc">${e(v.rfcTipo)}</span>` : ""}
    <span class="dp-mensaje ${v.rfcClase}">${e(v.rfcMensaje)}</span>
    ${v.mostrarVerificacion ? enlaceVerificar(URL_VALIDAR_RFC_SAT, v.rfcValor, "RFC", "Verificar en el SAT") : ""}`;
}

/* Selector del horario de atención. Cada bloque son unos días de la semana
   (botones que se prenden y apagan) y una hora de inicio y otra de fin, como
   al programar una alarma: en el celular cada hora abre la rueda del
   teléfono. Se pueden agregar más bloques (por ejemplo, Sáb con otro horario). */
export function altaHorario(v) {
  const bloques = v.form.horarioBloques;
  return `
    <label class="dp-horario-titulo">Horario de atención</label>
    ${bloques.map((b, i) => `
      <div class="dp-horario-bloque">
        <div class="dp-dias-chips" role="group" aria-label="Días del horario ${i + 1}">
          ${DIAS_SEMANA.map((dia, j) => `
            <button type="button" class="dp-dia-chip${b.dias.includes(j) ? " dp-sel" : ""}"
              data-accion="hor-dia" data-bloque="${i}" data-dia="${j}" aria-pressed="${b.dias.includes(j)}">${e(dia)}</button>`).join("")}
        </div>
        <div class="dp-horas">
          <label class="dp-hora">De <input type="time" data-hor="desde" data-bloque="${i}" value="${e(b.desde)}"></label>
          <label class="dp-hora">A <input type="time" data-hor="hasta" data-bloque="${i}" value="${e(b.hasta)}"></label>
          ${bloques.length > 1 ? `<button type="button" class="btn btn-secondary" data-accion="hor-quitar" data-bloque="${i}">Quitar</button>` : ""}
        </div>
      </div>`).join("")}
    <div class="dp-horario-pie">
      <button type="button" class="btn btn-secondary" data-accion="hor-agregar">+ Agregar otro horario</button>
      <span class="dp-nota" id="dp-horario-resumen">${e(v.horarioResumen)}</span>
    </div>`;
}

/* Documentos opcionales del alta. El <input type="file"> no conserva el
   archivo si se repinta, así que el archivo elegido vive en el estado de la
   pantalla y aquí solo se muestra su nombre. */
export function altaDocumentos(v) {
  const accept = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
  const elegir = (d, texto) => `
    <label class="dp-doc-elegir" for="dp-doc-${d.tipo}">${e(texto)}</label>
    <input type="file" id="dp-doc-${d.tipo}" class="dp-doc-input" data-documento="${d.tipo}" accept="${accept}">`;
  return `
    <h3 class="dp-subtitulo">Documentos (opcionales)</h3>
    <p class="dp-texto">PDF, JPG o PNG de hasta 5 MB.</p>
    <ul class="dp-documentos-carga">
      ${v.documentosAlta.map(d => `
        <li>
          <div class="dp-doc-titulo">${e(d.etiqueta)}</div>
          <div class="dp-nota">${e(d.ayuda)}</div>
          <div class="dp-doc-archivo">
            ${d.archivoNombre ? `
              <span class="dp-doc-nombre">${e(d.archivoNombre)} · ${e(d.archivoTamano)}${d.guardadoNombre ? " (reemplaza al actual al guardar)" : ""}</span>
              <button class="btn btn-secondary" data-accion="quitar-archivo-elegido" data-tipo="${d.tipo}">Quitar</button>`
            : d.guardadoNombre ? `
              <span class="dp-doc-nombre">✓ ${e(d.guardadoNombre)}</span>
              <button class="btn btn-secondary" data-accion="ver-documento" data-folio="${e(v.editandoFolio)}" data-tipo="${d.tipo}">Ver</button>
              <button class="btn btn-secondary" data-accion="quitar-documento" data-tipo="${d.tipo}">Quitar</button>
              ${elegir(d, "Reemplazar")}`
            : elegir(d, "Elegir archivo")}
          </div>
        </li>`).join("")}
    </ul>`;
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
  // Si el catálogo no cargó, se dice explícitamente en vez de dejar el combo
  // vacío sin explicación (ver cargarEntidadesAltaReal en datos.js).
  if (v.formEntidadesFallaron) return `<option value="">No se pudo cargar el catálogo. Reintenta.</option>`;
  return opcionesCatalogoTexto(v.formEntidades, v.form.estado);
}

export function opcionesMunicipio(v) {
  if (!v.form.estado) return `<option value="">Elige un estado primero</option>`;
  if (!v.formMunicipiosCargados) return `<option value="">Cargando…</option>`;
  if (!v.formMunicipios.length) return `<option value="">Sin municipios para este estado</option>`;
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

/* ---------- Fuera de la red (candidatos de Google Maps) ---------- */
export function opcionesEntidadFuera(v) {
  if (v.fueraEntidadesFallaron) return `<option value="">No se pudo cargar el catálogo. Reintenta.</option>`;
  return `<option value="">Selecciona un estado</option>`
    + opcionesCatalogoTexto(v.fueraEntidades, v.fueraForm.codEnt);
}

export function opcionesMunicipioFuera(v) {
  if (!v.fueraForm.codEnt) return `<option value="">Elige un estado primero</option>`;
  // "Cargando…" solo mientras de verdad se está pidiendo; si ya se pidió y
  // vino vacío, se dice eso en vez de dejar el combo girando para siempre.
  if (!v.fueraMunicipiosCargados) return `<option value="">Cargando…</option>`;
  if (!v.fueraMunicipios.length) return `<option value="">Sin municipios para este estado</option>`;
  // Sin municipio = toda la entidad: útil cuando en el municipio no hay nada.
  return `<option value="">Todo el estado</option>`
    + opcionesCatalogoTexto(v.fueraMunicipios, v.fueraForm.codMun);
}

/* Las mismas especialidades del directorio (tarjetas + combo), en orden
   alfabético para encontrarlas rápido. El valor es el nombre: es lo que se
   le manda a Google como término de búsqueda. */
export function opcionesEspecialidadFuera(v) {
  if (!v.fueraEspecialidades.length) return `<option value="">Cargando…</option>`;
  const elegida = normalizarTexto(v.fueraForm.especialidad);
  return `<option value="">Selecciona una especialidad</option>`
    + v.fueraEspecialidades.map(x =>
      `<option value="${e(x)}"${normalizarTexto(x) === elegida ? " selected" : ""}>${e(x)}</option>`
    ).join("");
}

function _introFuera() {
  return `
    <div class="dp-vacio">
      <p class="dp-vacio-titulo">Elige estado y especialidad</p>
      <p class="dp-texto">Se consultará Google Maps (Places API): indexa el giro real del negocio, pero cada búsqueda tiene costo y puede incluir el nombre del médico y reseñas de pacientes.</p>
    </div>`;
}

function _sinResultadosFuera(v) {
  return `
    <div class="dp-vacio">
      <p class="dp-vacio-titulo">Sin resultados para esa búsqueda</p>
      <p class="dp-texto">Google Maps no reporta nada para «${e(v.fueraConsulta || v.fueraArea)}». Prueba con el municipio "Todo el estado" o con otro término.</p>
    </div>`;
}

/* Google no regresa teléfono en esta búsqueda (eso costaría una consulta de
   "Place Details" por cada candidato -- ver el porqué en
   app/services/google_maps_service.py): en su lugar se da un enlace directo
   a la ficha del lugar en Google Maps.

   La primera columna lleva el MISMO número que el pin del mapa, para poder
   seguir un consultorio al alternar Mapa/Lista sin perder el hilo. Es la
   posición en esta lista, así que ambos lados deben recorrerla en el mismo
   orden (ver el .map con índice). */
function _tablaGoogle(v) {
  return `
    <div class="dp-aviso-candidatos">
      <span class="badge pendiente">Fuera de la red</span>
      <p class="dp-texto">
        ${e(String(v.fueraCandidatos.length))} establecimiento(s) según ${e(v.fueraFuente)} · área ${e(v.fueraArea)}.
        <b>No son proveedores del portal:</b> no tienen clave, no se les puede agendar y sus datos no se guardan.
        Esta búsqueda tiene costo por consulta y puede mostrar el nombre del médico y reseñas de pacientes.
      </p>
      <p class="dp-texto dp-aviso-alcance">
        No se trae el teléfono directo para no multiplicar el costo por cada candidato: usa
        <b>"Ver en Google Maps"</b> para consultarlo en la ficha pública del lugar.
      </p>
    </div>
    <div class="table-wrap">
      <table class="mini-table dp-tabla-candidatos">
        <thead>
          <tr><th class="dp-col-num">#</th><th>Establecimiento</th><th>Calificación</th><th>Domicilio</th><th>Enlace</th></tr>
        </thead>
        <tbody>
          ${v.fueraCandidatos.map((c, i) => `
            <tr>
              <td class="dp-col-num" data-label="#"><span class="dp-num-pin">${i + 1}</span></td>
              <td data-label="Establecimiento">
                <div class="dp-fuerte">${e(c.nombre || "Sin nombre registrado")}</div>
                ${c.abierto_ahora === true ? `<div class="dp-muted">Abierto ahora</div>` : c.abierto_ahora === false ? `<div class="dp-muted">Cerrado ahora</div>` : ""}
              </td>
              <td data-label="Calificación">
                ${c.calificacion != null ? `${e(String(c.calificacion))} ★ (${e(String(c.total_calificaciones || 0))})` : "Sin calificación"}
              </td>
              <td data-label="Domicilio">${e(c.direccion || "—")}</td>
              <td data-label="Enlace">
                ${c.enlace_maps ? `<a href="${e(c.enlace_maps)}" target="_blank" rel="noopener noreferrer">Ver en Google Maps</a>` : "—"}
              </td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

export function fueraResultadosCuerpo(v) {
  if (v.fueraBuscando) {
    return `<div class="spinner-row">Consultando Google Maps…</div>`;
  }
  if (v.fueraError) {
    return `
      <div class="dp-vacio">
        <p class="dp-vacio-titulo">No se pudo completar la búsqueda</p>
        <p class="dp-texto">${e(v.fueraError)}</p>
      </div>`;
  }
  if (!v.fueraBuscado) return _introFuera(v);
  if (!v.fueraCandidatos.length) return _sinResultadosFuera(v);

  // Selector Lista / Mapa: el mapa es la vista por default porque ubicar los
  // consultorios en la zona es lo que más ayuda a decidir a quién contactar.
  // Si esta fuente no puede dibujar mapa (Google sin llave del navegador) el
  // botón no se pinta: mejor una sola opción real que una que falle.
  const verMapa = v.fueraVista === "mapa" && v.fueraPuedeMapa;
  const selector = `
    <div class="dp-acciones dp-fuera-vista">
      ${v.fueraPuedeMapa ? `
      <div class="dp-seg" role="group" aria-label="Vista de resultados">
        <button type="button" class="dp-seg-opcion${verMapa ? " dp-sel" : ""}" data-accion="fuera-vista-mapa">Mapa</button>
        <button type="button" class="dp-seg-opcion${verMapa ? "" : " dp-sel"}" data-accion="fuera-vista-lista">Lista</button>
      </div>` : ""}
      <span class="dp-nota">${e(String(v.fueraCandidatos.length))} resultado(s) · ${e(v.fueraArea)}</span>
    </div>`;

  // Sin llave del navegador el mapa de Google no puede dibujarse: se explica
  // por qué se está mostrando la lista, en vez de dejar el botón "Mapa"
  // apagado sin razón aparente.
  const notaSinMapa = !v.fueraPuedeMapa
    ? `<p class="dp-texto dp-nota">El mapa de Google no está configurado en este servidor,
       así que los resultados se muestran en lista.</p>` : "";

  const contenido = verMapa
    ? `<div class="dp-mapa" id="dp-fuera-mapa"></div>`
    : _tablaGoogle(v);

  return selector + notaSinMapa + contenido;
}

export function pantallaFueraDeRed(v) {
  return `
    ${encabezado({
      volver: "← Volver al directorio", accionVolver: "ir-inicio",
      titulo: "Buscar fuera de la red",
      texto: "Establecimientos candidatos a contratar cuando la red no tiene cobertura en una zona. Es información pública (Google Maps): para incorporar a alguien hay que darlo de alta y validar su cédula profesional.",
    })}
    <div class="card tono-azul">
      <div class="card-body dp-fuera-form">
        <div class="dp-grid-campos">
          <div class="field dp-campo">
            <label for="dp-fr-estado">Estado</label>
            <select id="dp-fr-estado" data-campo-fuera="codEnt">${opcionesEntidadFuera(v)}</select>
          </div>
          <div class="field dp-campo">
            <label for="dp-fr-mun">Municipio</label>
            <select id="dp-fr-mun" data-campo-fuera="codMun">${opcionesMunicipioFuera(v)}</select>
          </div>
          <div class="field dp-campo">
            <label for="dp-fr-esp">Especialidad</label>
            <select id="dp-fr-esp" data-campo-fuera="especialidad">${opcionesEspecialidadFuera(v)}</select>
          </div>
        </div>
        <div class="dp-acciones dp-enviar">
          <button class="btn btn-primary" data-accion="buscar-fuera-de-red"${v.fueraPuedeBuscar && !v.fueraBuscando ? "" : " disabled"}>Buscar</button>
          <span class="dp-nota">${e(v.fueraPuedeBuscar ? "Listo para buscar." : "Elige un estado y una especialidad.")}</span>
        </div>
      </div>
    </div>
    <div class="card tono-verdeazul" id="dp-fuera-resultados"><div class="card-body">${fueraResultadosCuerpo(v)}</div></div>`;
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
        ...volverSegunPerfil(v),
        titulo: "Alta de médico",
        texto: "Registra tu consultorio en el directorio. La solicitud queda en revisión y un Administrador la aprueba o la rechaza.",
      });
  if (v.registered) {
    return `
      ${cabecera}
      <div class="card tono-verde dp-confirmacion">
        <div class="card-body">
          <span class="badge seguimiento">Solicitud recibida</span>
          <h2 class="dp-titulo dp-titulo-medio">${e(v.regName)} quedó en revisión</h2>
          <p class="dp-texto">Folio ${e(v.regFolio)}. Puedes seguir el estatus en la bandeja de solicitudes.</p>
          <p class="dp-texto">${v.regDocumentos.length ? "Documentos adjuntos: " + e(v.regDocumentos.join(" y ")) + "." : "Sin documentos adjuntos."}</p>
          <div class="dp-acciones">
            <button class="btn btn-primary" data-accion="ir-solicitudes">Ver solicitudes</button>
            <button class="btn btn-secondary" data-accion="registrar-otro">Registrar otro médico</button>
          </div>
        </div>
      </div>`;
  }
  const f = v.form;
  const campo = (id, campoForm, etiqueta, placeholder, extra = "") => `
    <div class="field dp-campo">
      <label for="${id}">${e(etiqueta)}</label>
      <input type="text" id="${id}" data-campo="${campoForm}" placeholder="${e(placeholder)}" value="${e(f[campoForm])}" autocomplete="off" ${extra}>
    </div>`;
  const opciones = (lista, elegido) => lista.map(x => `<option value="${e(x)}"${x === elegido ? " selected" : ""}>${e(x)}</option>`).join("");
  return `
    ${cabecera}
    <div class="dp-dos-columnas dp-alta">
      <div class="card tono-azul">
        <div class="card-body dp-formulario">
          <p class="dp-nota">Todos los datos son obligatorios, excepto la cédula profesional, el RFC y los documentos.</p>
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
            ${campo("dp-ced", "cedula", "Cédula profesional (opcional)", "7 u 8 dígitos", 'maxlength="8" inputmode="numeric" pattern="[0-9]*"')}
            ${campo("dp-rfc", "rfc", "Cédula fiscal / RFC (opcional)", "GODE561231GR8", 'maxlength="13" autocapitalize="characters" spellcheck="false"')}
          </div>
          <div class="dp-verificacion" id="dp-alta-verificacion">${altaVerificacion(v)}</div>
          <div class="dp-verificacion dp-verificacion-rfc" id="dp-alta-rfc">${altaRfc(v)}</div>
          <h3 class="dp-subtitulo dp-subtitulo-espacio">Consultorio donde da la consulta</h3>
          ${campo("dp-consultorio", "consultorio", "Nombre del consultorio o clínica", "Consultorio 302", 'maxlength="120"')}
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
          ${campo("dp-calle", "calleNumExtInt", "Calle, No. Ext. y No. Int.", "Av. Vallarta 1450, Int. 302")}
          <div class="dp-grid-campos">
            ${campo("dp-colonia", "colonia", "Colonia", "Americana")}
            ${campo("dp-cp", "codigoPostal", "Código Postal", "44100", 'maxlength="5" inputmode="numeric" pattern="[0-9]*"')}
          </div>
          <div class="dp-grid-campos">
            ${campo("dp-tel", "phone", "Teléfono", "10 dígitos", 'maxlength="10" inputmode="tel" pattern="[0-9]*"')}
            ${campo("dp-mail", "email", "Correo electrónico", "consultorio@correo.mx", 'maxlength="120" inputmode="email" autocapitalize="none" spellcheck="false"')}
          </div>
          <div class="field dp-campo">
            <label for="dp-costo">Costo aproximado de consulta</label>
            <select id="dp-costo" data-campo="costoConsulta">
              <option value="">Selecciona un rango</option>
              ${COSTOS_APROXIMADOS.map(c => `<option value="${e(c.valor)}"${c.valor === f.costoConsulta ? " selected" : ""}>${e(c.etiqueta)}</option>`).join("")}
            </select>
          </div>
          <div class="field dp-campo dp-horario" id="dp-alta-horario" data-campo="horario">${altaHorario(v)}</div>
          <div class="dp-acciones dp-enviar">
            <button class="btn btn-primary" data-accion="enviar-alta">${v.editando ? "Guardar cambios" : "Enviar solicitud de alta"}</button>
            ${v.editando ? `<button class="btn btn-secondary" data-accion="cancelar-edicion">Cancelar</button>` : ""}
            <span class="dp-nota" id="dp-alta-nota">${altaNota(v)}</span>
          </div>
        </div>
      </div>
      <aside class="card tono-morado">
        <div class="card-body dp-lateral">
          <div id="dp-alta-documentos">${altaDocumentos(v)}</div>
        </div>
      </aside>
    </div>`;
}

/* ---------- Ficha del médico y agenda (modal) ---------- */

/* Lista del paso "¿Para qué expediente?" (se repinta sola al buscar). */
export function listaExpedientesCita(v) {
  if (v.expedientesCita === null) return `<div class="spinner-row">Consultando expedientes…</div>`;
  if (!v.expedientesTotal) {
    return `<p class="dp-nota">No hay expedientes esperando cita: solo aparecen los que están «En Espera de Respuesta» o «Seguimiento de Cita» y todavía no tienen una.</p>`;
  }
  if (!v.expedientesCita.length) return `<p class="dp-nota">Ningún expediente coincide con «${e(v.expedienteBusqueda)}».</p>`;
  return v.expedientesCita.map(x => `
    <button type="button" class="dp-exp-opcion" data-accion="elegir-expediente" data-cl="${e(x.cl)}">
      <span class="dp-exp-titulo">
        <span class="dp-tabular">Exp. ${e(x.cl)}</span>
        ${x.coincide ? `<span class="badge seguimiento">Misma especialidad</span>` : ""}
      </span>
      <span class="dp-fuerte">${e(x.paciente)}</span>
      <span class="dp-nota">${e(x.especialidad)} · ${e(x.zona)} · ${e(x.estatus)}${x.cuenta ? " · " + e(x.cuenta) : ""}</span>
    </button>`).join("");
}

/* Para qué expediente es la cita, y si no cuadra con el médico elegido. */
function bloqueExpedienteDeLaCita(v) {
  const x = v.citaExpediente;
  if (!x) return "";
  return `
    <div class="dp-cita-expediente">
      <div>
        <span class="dp-subtitulo-chico">Cita para el expediente ${e(x.cl)}</span>
        <div class="dp-fuerte">${e(x.paciente)}</div>
        <div class="dp-nota">${e(x.especialidad)} · ${e(x.zona)}</div>
      </div>
      ${x.puedeCambiar ? `<button class="btn btn-secondary" data-accion="cambiar-expediente">Cambiar expediente</button>` : ""}
    </div>
    ${v.citaAvisos.map(a => `<p class="dp-aviso-coincidencia">${e(a)}</p>`).join("")}`;
}

export function fichaCuerpo(v) {
  const cabecera = `
    <span class="badge ${clasePorOrigen(v.detailOrigen)}">${e(v.detailSource)}</span>
    <p class="dp-ficha-sub">${e(v.detailSpecialty)}${v.detailCedula ? " · Cédula " + e(v.detailCedula) : ""}</p>`;
  if (v.bookingExpediente) {
    return `
      ${cabecera}
      <div class="dp-ficha-seccion">
        <h3 class="dp-subtitulo">¿Para qué expediente es la cita?</h3>
        <p class="dp-nota">Al confirmar, la cita queda ligada al expediente y sus datos se copian a Observaciones de su Seguimiento.</p>
        <div class="field">
          <label for="dp-exp-buscar">Buscar por número de expediente o paciente</label>
          <input type="search" id="dp-exp-buscar" value="${e(v.expedienteBusqueda)}" autocomplete="off" placeholder="Ej. 4518823 o Juan Pérez">
        </div>
        <div class="dp-exp-lista" id="dp-exp-lista">${listaExpedientesCita(v)}</div>
      </div>`;
  }
  if (v.bookingPick) {
    return `
      ${cabecera}
      ${bloqueExpedienteDeLaCita(v)}
      <div class="dp-ficha-seccion">
        <p class="dp-nota">Horario de atención: ${e(v.detailSchedule)}</p>
        <h3 class="dp-subtitulo">Elige día</h3>
        <div class="dp-dias">
          ${v.bookingDays.map(day => `
            <button class="dp-opcion dp-dia${day.elegido ? " dp-sel" : ""}" data-accion="elegir-dia" data-indice="${day.indice}"${day.disabled ? " disabled" : ""}>
              <span class="dp-etiqueta">${e(day.dow)}</span>
              <span class="dp-dia-num">${e(day.num)}</span>
              <span class="dp-dia-cupo">${e(day.slots)}</span>
            </button>`).join("")}
        </div>
        <h3 class="dp-subtitulo dp-subtitulo-espacio">Horarios sugeridos</h3>
        <div class="dp-horarios">
          ${v.bookingSlots.length
            ? v.bookingSlots.map(sl => `
            <button class="dp-horario${sl.elegido ? " dp-sel" : ""}" data-accion="elegir-horario" data-valor="${e(sl.label)}">${e(sl.label)}</button>`).join("")
            : v.diaSinAtencion
              ? `<span class="dp-nota">El médico no atiende ese día: elige otro.</span>`
              : `<span class="dp-nota">No quedan horarios sugeridos libres este día: captura la hora abajo.</span>`}
        </div>
        <h3 class="dp-subtitulo dp-subtitulo-espacio">¿Otro día u otra hora?</h3>
        <p class="dp-nota">Si el médico te confirma por teléfono una fecha u hora distinta (por ejemplo, las 12:45), captúrala aquí. Debe quedar dentro de su horario de atención.</p>
        <div class="dp-cita-libre">
          <div class="field">
            <label for="dp-fecha-libre">Fecha</label>
            <input type="date" id="dp-fecha-libre" min="${e(v.bookingFechaMin)}" max="${e(v.bookingFechaMax)}" value="${e(v.bookingFechaLibre)}">
          </div>
          <div class="field">
            <label for="dp-hora-libre">Hora</label>
            <input type="time" id="dp-hora-libre" value="${e(v.bookingHoraLibre)}">
          </div>
        </div>
      </div>`;
  }
  if (v.bookingDone) {
    return `
      ${cabecera}
      <div class="dp-ficha-seccion">
        <span class="badge seguimiento">Cita confirmada</span>
        <p class="dp-cita-resumen">${e(v.bookingSummary)}</p>
        <p class="dp-texto">Folio ${e(v.bookingFolio)} · ${e(v.detailClinic)}</p>        <p class="dp-texto">${e(v.detailDomicilioCalle)}, ${e(v.detailDomicilioResto)}.</p>
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
  if (v.bookingExpediente) {
    return `
      <button class="btn btn-secondary" data-accion="volver-ficha">Volver</button>
      <span class="dp-nota">Elige el expediente para continuar.</span>`;
  }
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
