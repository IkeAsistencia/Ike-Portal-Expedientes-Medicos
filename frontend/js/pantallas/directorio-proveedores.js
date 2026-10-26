/* Pantalla: Directorio de Proveedores (perfiles Proveedor y Administrador).
   Es la maqueta del prototipo "Directorio de Proveedores" (búsqueda de
   especialistas por zona y especialidad) metida dentro del portal: mismos
   textos y mismo comportamiento que el original, con el diseño del portal.
   NO toca expedientes, correos ni usuarios -- pero SÍ tiene conexión real
   con el backend (ver js/directorio/datos.js):
     - Búsqueda/resultados: leen el padrón real, con los dos orígenes
       juntos -- "Dentro de la red" (llegó en la carga de Excel que sube
       Administrador) y "Alta rápida" (alta aprobada en este portal, sin el
       proceso formal de convenio con IKE).
     - Alta de médico / Solicitudes: la solicitud, su estatus y su
       aprobación quedan guardados en este portal (nunca en el sistema
       central); al aprobarse, el médico entra al padrón con su propia
       clave (PRV-000001) y ya se le pueden agendar citas.
     - Citas: se guardan contra esa clave y los horarios libres los decide
       el servidor, así que dos personas no pueden tomar el mismo.
     - Métricas: se calculan del padrón cargado.
   NO queda nada simulado en la pantalla: lo único pendiente de conectar es
   la validación de la cédula contra el RNP de la SEP, y mientras tanto solo
   se valida el formato y así se le informa al usuario.

   Sub-pantallas internas (por estado, no por hash): home, zone, results,
   compare, metrics, admin (Solicitudes) y register (Alta de médico), más la
   ficha/agenda del médico (modal) y la barra de comparar. Los datos y
   generadores están en js/directorio/datos.js y las plantillas en
   js/directorio/vistas.js. */
import { crearModal } from "../componentes/modal.js";
import {
  RECENT_KEY,
  visible, formularioVacio, cargarCatalogoReal,
  cargarSolicitudesReales, enviarSolicitudAlta, actualizarEstatusSolicitud,
  editarSolicitudAlta,
  subirDocumentoSolicitud, quitarDocumentoSolicitud, descargarDocumentoSolicitud,
  clavesDeUbicacion,
  cargarAgenda, agendarCita, cargarExpedientesParaCita,
  cargarEntidadesAltaReal, cargarMunicipiosAltaReal,
  buscarFueraDeRed, buscarFueraDeRedGoogle, resolverBusquedaDeExpediente,
  cargarEspecialidadesKpi, olvidarEspecialidadesKpi, todasLasEspecialidades,
} from "../directorio/datos.js";
import * as V from "../directorio/vistas.js";
import {
  revisarFormularioAlta, RESTRICCIONES_ALTA, DOCUMENTOS_ALTA, bloqueHorarioVacio, DOCUMENTO_TIPOS_PERMITIDOS, DOCUMENTO_TAMANO_MAXIMO,
} from "../directorio/validacion-alta.js";
import { toast } from "../core/toast.js";
import { esPerfilAdministrador } from "../core/sesion.js";
import { coordinacionActual, iniciarCoordinacion, terminarCoordinacion } from "../core/coordinar-cita.js";
import { abrirSeguimiento, rellenarObservacionesConCita } from "./seguimiento.js";

const PLANTILLA = `
  <div class="dp-directorio" id="dp-raiz">
    <div class="dp-barra" id="dp-barra"></div>
    <div id="dp-aviso-cita"></div>
    <div id="dp-cuerpo"></div>
    <footer class="dp-pie" id="dp-pie"></footer>
    <div class="dp-barra-comparar hidden" id="dp-barra-comparar"></div>
  </div>`;

const RUTA_MAPA = "js/directorio/mapa-zona.html";
const MAX_RECIENTES = 5;
const MAX_COMPARAR = 3;

let raiz = null;
let modalFicha = null;
let marcoMapa = null;    // <iframe> del mapa (solo existe con la vista Mapa en Resultados)
let generacion = 0;      // al reiniciar se incrementa: los setTimeout pendientes ya no aplican
let estado = estadoInicial();

const $ = (id) => document.getElementById(id);

/* ---------- Estado (el mismo "state" inicial del original) ---------- */
function estadoInicial() {
  return {
    screen: "home", specialty: null, estado: null, municipio: null,
    // cl_especialidad del catálogo cuando se llegó por tarjeta o por el
    // combo: con eso se filtra el padrón (ver raw() en datos.js), para que
    // el conteo de la tarjeta y los resultados coincidan.
    specialtyId: null,
    query: "", searchTerm: null, recent: [],
    view: "list",
    // Solo los filtros que se resuelven con datos reales del padrón (ver
    // visible() en datos.js).
    filters: { maxPrice: 9999, tele: false, seguro: false, orden: "nombre" },
    compare: [],
    detail: null, bookingStep: "idle", bookingDay: null, bookingSlot: null,
    // La cita también se puede capturar en CUALQUIER fecha y hora: la fecha y
    // la hora libres (y los horarios sugeridos de esa fecha, si se eligió otra).
    bookingFechaLibre: "", bookingHoraLibre: "", agendaLibre: null,
    // Agenda real del médico abierto (la manda el servidor, ver cargarAgenda).
    agenda: [], bookingFolio: null, bookingGuardando: false,
    // Paso "¿Para qué expediente?" al agendar sin venir de uno: la lista (null
    // mientras se consulta) y lo que se escribió en su buscador.
    expedientesCita: null, expedienteBusqueda: "",
    registered: null, requests: [],
    // Folio de la solicitud que se está corrigiendo (botón "Editar" de
    // Solicitudes); null = la pantalla de alta captura una nueva.
    editandoFolio: null,
    form: formularioVacio(),
    // Documentos opcionales del alta: los archivos elegidos (se suben al
    // guardar) y, al editar, los que la solicitud ya tiene en el servidor.
    archivosAlta: {}, documentosEditando: {},
    // Ya se intentó enviar: a partir de ahí el RFC muestra su error aunque
    // todavía esté corto (antes de eso solo se muestra al tener 12 o más).
    altaIntento: false, enviandoAlta: false,
    // Búsqueda fuera de la red (candidatos del DENUE o de Google Maps, a
    // elegir -- ver datos.js). No se guardan: viven solo en este estado
    // mientras dura la consulta. fueraOrigen decide cuál de las dos fuentes
    // se usa; "denue" por default porque es gratis y no requiere llave.
    fueraForm: { codEnt: "", codMun: "", especialidad: "" },
    fueraOrigen: "denue",
    fueraResultados: null, fueraBuscando: false, fueraError: null,
    // Aviso de "Coordinar cita" (ver core/coordinar-cita.js): dónde se detuvo
    // la búsqueda y si conviene ofrecer buscar fuera de la red.
    coordNota: "", coordFuera: false,
  };
}

/* Salir del modo "Editar": el formulario de alta vuelve a estar en blanco
   para capturar uno nuevo. Se aplica al navegar con la barra, para no
   quedarse editando un folio sin darse cuenta. */
const sinEdicion = () => ({
  editandoFolio: null, form: formularioVacio(),
  archivosAlta: {}, documentosEditando: {}, altaIntento: false,
});

/* Búsquedas recientes en localStorage. Si el navegador no deja leer o
   escribir (modo privado, almacenamiento bloqueado), simplemente no hay
   recientes: la pantalla funciona igual. */
function leerRecientes() {
  try {
    const crudo = localStorage.getItem(RECENT_KEY);
    if (!crudo) return [];
    const lista = JSON.parse(crudo);
    return Array.isArray(lista) ? lista.filter(r => typeof r === "string").slice(0, MAX_RECIENTES) : [];
  } catch (e) {
    return [];
  }
}

function recordar(termino) {
  const t = termino.trim();
  if (!t) return;
  const siguiente = [t].concat(estado.recent.filter(r => r.toLowerCase() !== t.toLowerCase())).slice(0, MAX_RECIENTES);
  estado.recent = siguiente;
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(siguiente)); } catch (e) { /* sin almacenamiento */ }
}

const ponerFiltros = (cambios) => { estado.filters = Object.assign({}, estado.filters, cambios); };
const ponerFormulario = (cambios) => { estado.form = Object.assign({}, estado.form, cambios); };

/* ---------- Foco ----------
   Al repintar una zona con innerHTML los botones/campos se vuelven a crear;
   se guarda cuál tenía el foco (y el cursor, si es campo de texto) para
   devolvérselo al nuevo elemento equivalente. */
function claveFoco(el) {
  if (el.id) return "#" + el.id;
  const d = el.dataset || {};
  return [d.accion, d.valor, d.id, d.indice, d.filtro, d.campo, d.bloque, d.dia, d.hor].join("|");
}

function capturarFoco() {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  if (!raiz.contains(el) && !modalFicha.elemento.contains(el)) return null;
  let inicio = null, fin = null;
  try { inicio = el.selectionStart; fin = el.selectionEnd; } catch (e) { /* no es campo de texto */ }
  return { el, clave: claveFoco(el), inicio, fin };
}

function restaurarFoco(foco) {
  if (!foco || document.activeElement === foco.el) return;
  const candidatos = [...raiz.querySelectorAll("button, input, select"), ...modalFicha.elemento.querySelectorAll("button, input, select")];
  const nuevo = candidatos.find(c => claveFoco(c) === foco.clave);
  if (!nuevo || nuevo.disabled) return;
  nuevo.focus({ preventScroll: true });
  if (foco.inicio !== null && foco.inicio !== undefined) {
    try { nuevo.setSelectionRange(foco.inicio, foco.fin); } catch (e) { /* no aplica */ }
  }
}

/* ---------- Pintado ---------- */
/* El Administrador usa del directorio solo Solicitudes, Alta de médico y
   Métricas (la Carga del catálogo es otra pantalla). Buscar, ver fichas,
   comparar y agendar son del Proveedor: si por cualquier camino se intenta
   llegar a esas pantallas, se queda en Solicitudes. El servidor lo exige
   igual (ver _requerir_proveedor en app/routers/directorio_proveedores.py). */
const PANTALLAS_SOLO_PROVEEDOR = ["home", "zone", "results", "compare", "fuera"];

function restringirAdministrador() {
  if (!esPerfilAdministrador()) return;
  if (PANTALLAS_SOLO_PROVEEDOR.includes(estado.screen)) estado.screen = "admin";
  estado.detail = null;
  estado.compare = [];
}

function pintar() {
  if (!raiz) return;
  restringirAdministrador();
  const foco = capturarFoco();
  const v = V.calcular(estado);

  $("dp-barra").innerHTML = V.barra(v);
  $("dp-aviso-cita").innerHTML = V.avisoCoordinacion(v);
  pintarPantalla(v);
  $("dp-pie").innerHTML = V.pie(v);

  const barraComparar = $("dp-barra-comparar");
  barraComparar.classList.toggle("hidden", !v.showCompareBar);
  barraComparar.innerHTML = v.showCompareBar ? V.barraComparar(v) : "";

  pintarFicha(v);
  marcarInvalidosAlta();
  restaurarFoco(foco);
  enviarMapa();
}

/* Tras intentar enviar, marca en rojo los campos del alta que faltan o están
   mal; se quitan solos conforme se corrigen. */
function marcarInvalidosAlta() {
  if (estado.screen !== "register" || estado.registered) return;
  const malos = estado.altaIntento ? new Set(revisarFormularioAlta(estado.form).map(f => f.campo)) : new Set();
  raiz.querySelectorAll("[data-campo]").forEach(el => {
    if (malos.has(el.dataset.campo)) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  });
}

function pintarPantalla(v) {
  const cuerpo = $("dp-cuerpo");
  const anterior = cuerpo.dataset.pantalla;
  if (v.screen === "results") {
    pintarResultados(v, cuerpo);
  } else {
    const plantillas = {
      home: V.pantallaInicio, zone: V.pantallaZona, compare: V.pantallaComparar,
      metrics: V.pantallaMetricas, admin: V.pantallaSolicitudes, register: V.pantallaAlta,
      fuera: V.pantallaFueraDeRed,
    };
    cuerpo.innerHTML = plantillas[v.screen](v);
    cuerpo.dataset.pantalla = v.screen;
    marcoMapa = null;
  }
  // Al cambiar de sub-pantalla se regresa arriba (el scroll vive en .content).
  if (anterior && anterior !== v.screen) raiz.closest(".content")?.scrollTo(0, 0);
}

function pintarResultados(v, cuerpo) {
  if (cuerpo.dataset.pantalla !== "results") {
    cuerpo.innerHTML = V.esqueletoResultados();
    cuerpo.dataset.pantalla = "results";
    marcoMapa = null;
  }
  $("dp-res-cabecera").innerHTML = V.cabeceraResultados(v);
  $("dp-res-filtros").innerHTML = V.filtrosResultados(v);
  $("dp-res-conteo").innerHTML = V.conteoResultados(v);

  // El iframe del mapa se crea al pasar a la vista Mapa y se quita al volver
  // a Lista (igual que el original). Con los filtros NO se recarga: solo se
  // le manda la lista nueva por postMessage (ver enviarMapa).
  const zonaMapa = $("dp-res-mapa");
  if (v.viewMap) {
    zonaMapa.classList.remove("hidden");
    if (!marcoMapa) {
      marcoMapa = document.createElement("iframe");
      marcoMapa.title = "Mapa de la zona";
      marcoMapa.className = "dp-mapa-marco";
      marcoMapa.addEventListener("load", enviarMapa);
      marcoMapa.src = RUTA_MAPA;
      zonaMapa.appendChild(marcoMapa);
    }
  } else {
    zonaMapa.classList.add("hidden");
    zonaMapa.innerHTML = "";
    marcoMapa = null;
  }
  $("dp-res-lista").innerHTML = v.viewList ? V.listaResultados(v) : "";
}

function pintarFicha(v) {
  const overlay = modalFicha.elemento;
  if (!v.hasDetail) {
    // Se oculta directo (sin modal.cerrar) para no volver a disparar alCerrar.
    overlay.classList.add("hidden");
    return;
  }
  modalFicha.ponerTitulo(v.detailName);
  overlay.querySelector(".modal-body").innerHTML = V.fichaCuerpo(v);
  overlay.querySelector(".modal-footer").innerHTML = V.fichaPie(v);
  overlay.classList.remove("hidden");
}

/* Lista de la zona al iframe del mapa. Solo a nuestro propio origen. */
function enviarMapa() {
  if (!marcoMapa || !marcoMapa.contentWindow || estado.view !== "map") return;
  marcoMapa.contentWindow.postMessage({
    type: "zona", estado: estado.estado, municipio: estado.municipio,
    doctors: visible(estado).map(d => ({
      id: d.id, name: d.name, specialty: d.specialty, clinic: d.clinic, municipio: d.municipio,
      price: d.price, origen: d.origen,
      // Coordenadas reales del padrón (null si el proveedor no las trae).
      latitud: d.latitud, longitud: d.longitud,
    })),
  }, location.origin);
}

/* Repintados parciales mientras se escribe (sin tocar el campo). */
function pintarSugerencias() {
  const zona = $("dp-sugerencias");
  if (zona) zona.innerHTML = V.sugerencias(V.calcularSugerencias(estado));
}

function pintarDependientesAlta() {
  if (estado.screen !== "register" || estado.registered) return;
  const foco = capturarFoco();
  const v = V.calcular(estado);
  $("dp-alta-verificacion").innerHTML = V.altaVerificacion(v);
  $("dp-alta-rfc").innerHTML = V.altaRfc(v);
  $("dp-alta-documentos").innerHTML = V.altaDocumentos(v);
  marcarInvalidosAlta();
  $("dp-alta-nota").innerHTML = V.altaNota(v);
  restaurarFoco(foco);
}

/* ---------- Acciones (mismo efecto que los handlers del original) ---------- */
function irA(cambios) {
  // La nota del aviso explica dónde se detuvo la búsqueda al llegar; en cuanto
  // la persona elige otra especialidad, estado, municipio o pantalla, ya no aplica.
  if (!("coordNota" in cambios) && ["screen", "specialty", "estado", "municipio"].some(k => k in cambios)) {
    estado.coordNota = "";
    estado.coordFuera = false;
  }
  Object.assign(estado, cambios);
  pintar();
}

/* ---------- Coordinar cita desde un expediente ----------
   Se llega aquí desde el botón "Coordinar cita" de Seguimiento (ver
   core/coordinar-cita.js): la búsqueda arranca con los datos del expediente y,
   al confirmar la cita, se vuelve a Seguimiento con sus datos ya copiados en
   Observaciones. */
function aplicarCoordinacion() {
  const ctx = coordinacionActual();
  if (!ctx) return;
  const r = resolverBusquedaDeExpediente(ctx);
  irA({
    // Filtros y comparador en blanco: que lo de una visita anterior no esconda médicos.
    detail: null, searchTerm: null, view: "list", compare: [],
    filters: { maxPrice: 9999, tele: false, seguro: false, orden: "nombre" },
    screen: r.screen,
    specialty: r.especialidad ? r.especialidad.descripcion : null,
    specialtyId: r.especialidad ? Number(r.especialidad.cl_especialidad) : null,
    estado: r.estado, municipio: r.municipio,
    coordNota: r.nota, coordFuera: r.fuera,
  });
}

async function volverAlExpediente(textoCita, folio) {
  const ctx = terminarCoordinacion();
  irA({
    detail: null, bookingStep: "idle", bookingDay: null, bookingSlot: null,
    agenda: [], bookingFolio: null, bookingGuardando: false, coordNota: "", coordFuera: false,
  });
  if (!ctx) return;
  try {
    await abrirSeguimiento(ctx.record, ctx.fuente);
  } catch (err) {
    toast("No se pudo regresar al expediente: " + err.message, "error");
    return;
  }
  if (textoCita) {
    rellenarObservacionesConCita(textoCita);
    toast(
      `Cita ${folio} agendada. Los datos se copiaron a Observaciones: revísalos, agrega tus notas y presiona «Actualizar Seguimiento».`,
      "success", 9000
    );
  }
}

function buscar(termino) {
  recordar(termino);
  irA({ screen: "results", searchTerm: termino, query: termino, specialty: null });
}

/* La solicitud se guarda de verdad en el portal (ver enviarSolicitudAlta en
   datos.js). De la cédula y el RFC solo se valida el formato, al escribir y
   otra vez al enviar.

   El mismo botón guarda los cambios cuando se entró por "Editar"
   (estado.editandoFolio), en vez de crear una solicitud nueva.

   Los documentos elegidos se suben DESPUÉS de guardar la solicitud (necesitan
   su folio). Si alguno falla, la solicitud ya quedó guardada: se avisa cuál. */
async function enviarAlta() {
  if (estado.enviandoAlta) return;
  estado.altaIntento = true;
  const faltas = revisarFormularioAlta(estado.form);
  if (faltas.length) {
    pintarDependientesAlta();
    const primero = raiz.querySelector(`[data-campo="${faltas[0].campo}"]`);
    if (primero) {
      if (primero.matches("input, select, textarea")) primero.focus({ preventScroll: false });
      else primero.scrollIntoView({ block: "center" });
    }
    toast(
      faltas.length === 1 ? faltas[0].mensaje
        : `Faltan datos por completar o corregir: ${faltas.map(f => f.etiqueta).join(", ")}.`,
      "error", 7000
    );
    return;
  }
  const fm = estado.form;
  estado.enviandoAlta = true;
  try {
    const editando = estado.editandoFolio;
    const folio = editando || (await enviarSolicitudAlta(fm)).folio;
    if (editando) await editarSolicitudAlta(editando, fm);
    const { subidos, fallas } = await subirArchivosElegidos(folio);
    fallas.forEach(f => toast(`La solicitud ${folio} se guardó, pero no se pudo subir «${f.etiqueta}»: ${f.motivo}`, "error", 9000));
    if (editando) {
      toast("Solicitud " + editando + " actualizada.", "success");
      irA({ screen: "admin", ...sinEdicion() });
      await cargarSolicitudes();
      return;
    }
    irA({ registered: { name: fm.name || "El médico", folio, documentos: subidos }, archivosAlta: {}, altaIntento: false });
    cargarSolicitudes();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    estado.enviandoAlta = false;
  }
}

async function subirArchivosElegidos(folio) {
  const subidos = [], fallas = [];
  for (const doc of DOCUMENTOS_ALTA) {
    const archivo = estado.archivosAlta[doc.tipo];
    if (!archivo) continue;
    try {
      await subirDocumentoSolicitud(folio, doc.tipo, archivo);
      subidos.push(doc.etiqueta);
    } catch (err) {
      fallas.push({ etiqueta: doc.etiqueta, motivo: err.message });
    }
  }
  return { subidos, fallas };
}

/* Archivo elegido en el alta: se revisa aquí (formato y tamaño) para avisar
   antes de enviar; el servidor lo vuelve a revisar al subirlo. */
function elegirDocumento(input) {
  const tipo = input.dataset.documento;
  const archivo = input.files && input.files[0];
  if (!archivo) return;
  if (!DOCUMENTO_TIPOS_PERMITIDOS.includes(archivo.type)) {
    toast("Formato no permitido. Solo se aceptan PDF, JPG o PNG.", "error");
    input.value = "";
    return;
  }
  if (archivo.size > DOCUMENTO_TAMANO_MAXIMO) {
    toast("El archivo supera el máximo permitido de 5 MB.", "error");
    input.value = "";
    return;
  }
  estado.archivosAlta = { ...estado.archivosAlta, [tipo]: archivo };
  pintarDependientesAlta();
}

function quitarArchivoElegido(tipo) {
  const { [tipo]: _, ...resto } = estado.archivosAlta;
  estado.archivosAlta = resto;
  pintarDependientesAlta();
}

/* ---------- Horario de atención (selector de días y horas) ---------- */
function pintarHorario() {
  const zona = $("dp-alta-horario");
  if (!zona) return;
  const foco = capturarFoco();
  const v = V.calcular(estado);
  zona.innerHTML = V.altaHorario(v);
  $("dp-alta-nota").innerHTML = V.altaNota(v);
  marcarInvalidosAlta();
  restaurarFoco(foco);
}

function cambiarBloquesHorario(cambio) {
  const bloques = estado.form.horarioBloques.map(b => ({ ...b, dias: [...b.dias] }));
  cambio(bloques);
  ponerFormulario({ horarioBloques: bloques });
  pintarHorario();
}

const alternarDia = (el) => cambiarBloquesHorario(bloques => {
  const b = bloques[Number(el.dataset.bloque)], dia = Number(el.dataset.dia);
  b.dias = b.dias.includes(dia) ? b.dias.filter(d => d !== dia) : [...b.dias, dia].sort((x, y) => x - y);
});
const agregarHorario = () => cambiarBloquesHorario(bloques => bloques.push(bloqueHorarioVacio()));
const quitarHorario = (el) => cambiarBloquesHorario(bloques => bloques.splice(Number(el.dataset.bloque), 1));

/* La hora se guarda al terminar de elegirla (evento "change"): repintar a cada
   cambio del selector de hora lo cerraría. Solo se refresca el resumen. */
function cambiarHoraHorario(el) {
  const b = estado.form.horarioBloques[Number(el.dataset.bloque)];
  if (!b) return;
  b[el.dataset.hor] = el.value;
  const v = V.calcular(estado);
  const resumen = $("dp-horario-resumen");
  if (resumen) resumen.textContent = v.horarioResumen;
  $("dp-alta-nota").innerHTML = V.altaNota(v);
  marcarInvalidosAlta();
}

/* Quita un documento que la solicitud YA tiene en el servidor (al editar). */
async function quitarDocumentoGuardado(tipo) {
  const folio = estado.editandoFolio;
  if (!folio) return;
  try {
    await quitarDocumentoSolicitud(folio, tipo);
    const { [tipo]: _, ...resto } = estado.documentosEditando;
    estado.documentosEditando = resto;
    pintarDependientesAlta();
    cargarSolicitudes();
  } catch (err) {
    toast(err.message, "error");
  }
}

/* Abre el documento en otra pestaña. La pestaña se abre ANTES de pedir el
   archivo: abrirla después de esperar la descarga la bloquea el navegador. */
async function verDocumento(folio, tipo) {
  const ventana = window.open("", "_blank");
  try {
    const { blob } = await descargarDocumentoSolicitud(folio, tipo);
    const url = URL.createObjectURL(blob);
    if (ventana) ventana.location.href = url;
    else window.open(url, "_blank");
  } catch (err) {
    if (ventana) ventana.close();
    toast(err.message, "error");
  }
}

/* Botones "Verificar en el SAT / en la SEP": son enlaces normales (el sitio
   se abre solo); aquí además se copia el dato, porque esos sitios tienen
   captcha y no se les puede mandar ya capturado. */
async function copiarParaVerificar(el) {
  const valor = el.dataset.copiar;
  if (!valor) return;
  try {
    await navigator.clipboard.writeText(valor);
    toast(`Se copió ${valor}. Pégalo en el sitio que se abrió.`, "success");
  } catch (err) {
    toast(`Captura en el sitio el ${el.dataset.que}: ${valor}`, "", 9000);
  }
}

/* "Editar" (solo Administrador, y solo mientras la solicitud siga en
   revisión): abre el mismo formulario del alta con los datos cargados.
   La cédula entra como ya verificada -- lo fue al capturarse -- y si se
   cambia, alEscribir la vuelve a poner en "idle" y hay que verificarla
   otra vez. */
async function editarSolicitud(indice) {
  const solicitud = estado.requests[indice];
  if (!solicitud || !solicitud.form) return;
  irA({
    screen: "register",
    editandoFolio: solicitud.folio,
    // Estado y municipio se guardan por NOMBRE, pero los combos trabajan con
    // la clave del catálogo: se dejan vacíos y se llenan en cuanto se resuelven.
    form: { ...formularioVacio(), ...solicitud.form, estado: "", municipio: "" },
    registered: null,
    archivosAlta: {}, documentosEditando: { ...(solicitud.documentos || {}) }, altaIntento: false,
  });
  if (solicitud.form.estado) {
    const g = generacion;
    const claves = await clavesDeUbicacion(solicitud.form.estado, solicitud.form.municipio);
    if (g !== generacion || estado.editandoFolio !== solicitud.folio) return;
    ponerFormulario({ estado: claves.estado, municipio: claves.municipio });
    pintar();
    if (!claves.estado || (solicitud.form.municipio && !claves.municipio)) {
      toast("No se pudo ubicar el estado o el municipio guardados: vuelve a elegirlos.", "error", 7000);
    }
  }
}

function cancelarEdicion() {
  irA({ screen: "admin", ...sinEdicion() });
}

/* Aprobar/Rechazar sí actualiza el estatus real de la solicitud -- un
   médico recién aprobado se vuelve buscable en el Directorio en cuanto
   cargarCatalogoReal() lo vuelva a pedir (ver mapearProveedor, origen
   "portal"). */
async function cambiarEstatusSolicitud(indice, estatus) {
  const solicitud = estado.requests[indice];
  if (!solicitud) return;
  try {
    await actualizarEstatusSolicitud(solicitud.folio, estatus);
    await cargarSolicitudes();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function cargarSolicitudes() {
  estado.requests = await cargarSolicitudesReales();
  pintar();
}

/* ---------- Especialidades (tarjetas de KPI y combo) ----------
   Las tarjetas y el combo son la MISMA funcionalidad: las dos llegan aquí,
   con el nombre que se muestra y la clave del catálogo con la que se filtra
   el padrón (instrucción del usuario, 2026-10-20). */
function elegirEspecialidad(nombre, id) {
  if (!nombre) return;
  irA({
    screen: "zone", specialty: nombre,
    specialtyId: id ? Number(id) : null,
    estado: null, municipio: null, searchTerm: null,
  });
}

/* Las que no caben en la cuadrícula se eligen del combo: se busca el nombre
   por su clave para no depender del texto del <option> (que además lleva el
   KPI pegado). */
function elegirEspecialidadDelCombo(el) {
  const id = el.value;
  if (!id) return;
  const encontrada = todasLasEspecialidades().find(x => String(x.cl_especialidad) === String(id));
  if (encontrada) elegirEspecialidad(encontrada.descripcion, id);
}

/* ---------- Fuera de la red (candidatos del DENUE) ----------
   Se precarga el catálogo de Entidad al entrar, igual que en el Alta de
   médico: el DENUE necesita la clave del INEGI, que solo viene de ahí. */
function abrirFueraDeRed() {
  // Si se venía de una búsqueda por zona, se arrastra la especialidad para
  // no obligar a volver a escribirla.
  const especialidad = estado.specialty || estado.searchTerm || "";
  // Viniendo de un expediente, la zona por defecto es la suya.
  const ctx = coordinacionActual();
  const zona = {
    estado: estado.estado || (ctx && ctx.entidad) || null,
    municipio: estado.municipio || (ctx && ctx.municipio) || null,
  };
  irA({
    screen: "fuera", detail: null,
    fueraForm: { ...estado.fueraForm, especialidad: estado.fueraForm.especialidad || especialidad },
    fueraResultados: null, fueraError: null, fueraBuscando: false,
  });
  preseleccionarZonaFuera(zona);
}

/* El botón de "fuera de la red" sale justo cuando la red no tiene a nadie en
   una zona, así que esa zona se arrastra al formulario: obligar a volver a
   elegir estado y municipio invita a buscar en otro lado sin querer.

   El directorio trabaja con nombres ("Yucatán", "Valladolid") y el DENUE con
   las claves del catálogo real, por eso hay que emparejarlos por nombre. */
async function preseleccionarZonaFuera({ estado: nombreEntidad, municipio: nombreMunicipio }) {
  const g = generacion;
  const entidades = await cargarEntidadesAltaReal();
  if (g !== generacion || estado.screen !== "fuera") return;

  const entidad = nombreEntidad && !estado.fueraForm.codEnt
    ? entidades.find(x => comparable(x.descripcion) === comparable(nombreEntidad))
    : null;
  if (!entidad) {
    pintar();
    return;
  }

  estado.fueraForm = { ...estado.fueraForm, codEnt: entidad.clave, codMun: "" };
  pintar();

  const municipios = await cargarMunicipiosAltaReal(entidad.clave);
  if (g !== generacion || estado.screen !== "fuera") return;
  const municipio = nombreMunicipio
    ? municipios.find(x => comparable(x.descripcion) === comparable(nombreMunicipio))
    : null;
  if (municipio) estado.fueraForm = { ...estado.fueraForm, codMun: municipio.clave };
  pintar();
}

/* El catálogo viene en mayúsculas y sin acentos ("MERIDA"); el directorio
   los trae con acento ("Mérida"). */
function comparable(texto) {
  return (texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toUpperCase();
}

/* Cambiar de fuente (DENUE <-> Google Maps) limpia el resultado anterior:
   son dos búsquedas distintas y mostrar el aviso/tabla de la fuente vieja
   con la fuente nueva seleccionada confundiría al usuario. */
function elegirFueraOrigen(origen) {
  if (estado.fueraBuscando || estado.fueraOrigen === origen) return;
  irA({ fueraOrigen: origen, fueraResultados: null, fueraError: null });
}

async function buscarFuera() {
  const { codEnt, codMun, especialidad } = estado.fueraForm;
  if (!codEnt || (especialidad || "").trim().length < 3 || estado.fueraBuscando) return;

  irA({ fueraBuscando: true, fueraError: null, fueraResultados: null });
  const g = generacion;
  try {
    const buscar = estado.fueraOrigen === "google" ? buscarFueraDeRedGoogle : buscarFueraDeRed;
    const datos = await buscar({ codEnt, codMun, especialidad: especialidad.trim() });
    if (g !== generacion) return;
    irA({ fueraResultados: datos, fueraBuscando: false });
  } catch (err) {
    if (g !== generacion) return;
    irA({ fueraError: err.message, fueraBuscando: false });
  }
}

/* Los combos de esta pantalla no comparten el formulario del alta, por eso
   tienen su propio data-campo-fuera (ver cambiarCombo). */
async function cambiarComboFuera(el) {
  const campo = el.dataset.campoFuera;
  if (campo === "codEnt") {
    estado.fueraForm = { ...estado.fueraForm, codEnt: el.value, codMun: "" };
    estado.fueraResultados = null;
    pintar();
    await cargarMunicipiosAltaReal(el.value);
    if (estado.screen === "fuera") pintar();
    return;
  }
  estado.fueraForm = { ...estado.fueraForm, [campo]: el.value };
  pintar();
}

/* ---------- Agenda y citas (reales) ----------
   Los días/horarios libres los decide el servidor, así que se piden al abrir
   la agenda y se vuelven a pedir después de confirmar: si alguien más apartó
   un horario mientras tanto, se ve al instante. */
async function abrirAgenda(medico) {
  if (!medico) return;
  // Toda cita es para un expediente: si no se viene de uno (se entró al
  // directorio por el menú), primero se elige.
  if (!coordinacionActual()) {
    irA({
      detail: medico, bookingStep: "expediente", expedientesCita: null, expedienteBusqueda: "",
      bookingFolio: null, bookingGuardando: false,
    });
    const g = generacion;
    let lista = [];
    try {
      lista = await cargarExpedientesParaCita();
    } catch (err) {
      toast("No se pudieron consultar los expedientes: " + err.message, "error");
    }
    if (g !== generacion || estado.detail !== medico || estado.bookingStep !== "expediente") return;
    irA({ expedientesCita: lista });
    return;
  }
  irA({
    detail: medico, bookingStep: "pick", bookingDay: 0, bookingSlot: null,
    bookingFechaLibre: "", bookingHoraLibre: "", agendaLibre: null,
    agenda: [], bookingFolio: null, bookingGuardando: false,
  });
  const g = generacion;
  const agenda = await cargarAgenda(medico.clave);
  if (g !== generacion || estado.detail !== medico) return;
  // Arranca en el primer día que el médico atiende (no en uno que no).
  irA({ agenda, bookingDay: Math.max(0, agenda.findIndex(d => d.atiende !== false)) });
}

/* Se eligió el expediente en el paso "¿Para qué expediente?": a partir de
   aquí es igual que venir de Seguimiento (al confirmar se regresa a él). */
function elegirExpediente(el) {
  const record = (estado.expedientesCita || []).find(x => String(x.expediente) === el.dataset.cl);
  if (!record || !estado.detail) return;
  iniciarCoordinacion({ record, fuente: "menu", origen: "directorio" });
  abrirAgenda(estado.detail);
}

/* Solo cuando el expediente se eligió aquí; si se vino de Seguimiento, el
   expediente es ese y para cambiarlo se cancela la coordinación. */
function cambiarExpediente() {
  const ctx = coordinacionActual();
  if (!ctx || ctx.origen !== "directorio") return;
  terminarCoordinacion();
  abrirAgenda(estado.detail);
}

/* Elegido en el directorio, el expediente solo vale para ESTA cita: al cerrar
   la ficha o cancelar se suelta, para que el siguiente "Agendar" lo pregunte. */
function soltarExpedienteDelDirectorio() {
  const ctx = coordinacionActual();
  if (ctx && ctx.origen === "directorio") terminarCoordinacion();
}

function cancelarCoordinacion() {
  const ctx = coordinacionActual();
  if (ctx && ctx.origen === "directorio") {
    terminarCoordinacion();
    irA({ detail: null, bookingStep: "idle", coordNota: "", coordFuera: false });
    return;
  }
  volverAlExpediente(null);
}

async function confirmarCita() {
  const medico = estado.detail;
  if (!coordinacionActual()) {
    // No debería pasar (el paso del expediente va antes), pero sin expediente no hay cita.
    abrirAgenda(medico);
    return;
  }
  // Fecha y hora: las libres si se capturaron, y si no, el día y horario sugerido elegidos.
  const fecha = estado.bookingFechaLibre
    || ((estado.agenda || [])[estado.bookingDay == null ? 0 : estado.bookingDay] || {}).fecha;
  const hora = estado.bookingHoraLibre || estado.bookingSlot;
  if (!medico || !fecha || !hora || estado.bookingGuardando) return;

  irA({ bookingGuardando: true });
  try {
    const ctx = coordinacionActual();
    const cita = await agendarCita({ claveProveedor: medico.clave, fecha, hora, clExpediente: ctx.expediente });
    // Se regresa a Seguimiento del expediente con los datos de la cita ya
    // copiados en Observaciones (el servidor arma el texto).
    await volverAlExpediente(cita.observaciones_sugeridas, cita.folio);
  } catch (err) {
    // El caso típico: otra persona tomó ese horario (409). Se refresca la
    // agenda para que ya no aparezca como libre.
    toast(err.message, "error");
    const agenda = await cargarAgenda(medico.clave);
    const agendaLibre = estado.bookingFechaLibre
      ? (await cargarAgenda(medico.clave, estado.bookingFechaLibre))[0] || null
      : null;
    irA({ agenda, agendaLibre, bookingSlot: null, bookingHoraLibre: "", bookingGuardando: false });
  }
}

const medicoVisible = (id) => visible(estado).find(x => x.id === id) || null;

const ACCIONES = {
  // Barra propia y "volver"
  "ir-inicio": () => irA({ screen: "home", searchTerm: null, detail: null, ...sinEdicion() }),
  "ir-metricas": () => irA({ screen: "metrics", detail: null, ...sinEdicion() }),
  "ir-solicitudes": () => irA({ screen: "admin", detail: null, ...sinEdicion() }),
  "ir-alta": () => irA({ screen: "register", detail: null, ...sinEdicion() }),
  "volver-zona": () => irA({ screen: estado.searchTerm ? "home" : "zone", searchTerm: null }),
  "volver-resultados": () => irA({ screen: "results" }),

  // Coordinar cita desde un expediente: salir sin agendar
  "cancelar-coordinacion": cancelarCoordinacion,
  "elegir-expediente": elegirExpediente,
  "cambiar-expediente": cambiarExpediente,

  // Fuera de la red (candidatos del DENUE o de Google Maps)
  "ir-fuera-de-red": abrirFueraDeRed,
  "buscar-fuera-de-red": buscarFuera,
  "fuera-origen-denue": () => elegirFueraOrigen("denue"),
  "fuera-origen-google": () => elegirFueraOrigen("google"),

  // Inicio y zona
  "buscar": () => buscar(estado.query),
  "buscar-termino": (el) => buscar(el.dataset.valor),
  "elegir-especialidad": (el) => elegirEspecialidad(el.dataset.valor, el.dataset.id),
  "elegir-estado": (el) => irA({ estado: el.dataset.valor, municipio: null }),
  "elegir-municipio": (el) => irA({ screen: "results", municipio: el.dataset.valor, searchTerm: null }),

  // Resultados
  "vista-lista": () => irA({ view: "list" }),
  "vista-mapa": () => irA({ view: "map" }),
  "precio": (el) => { ponerFiltros({ maxPrice: Number(el.dataset.valor) }); pintar(); },
  "limpiar-filtros": () => { ponerFiltros({ maxPrice: 9999, tele: false, seguro: false }); pintar(); },
  "ficha": (el) => {
    const x = medicoVisible(el.dataset.id);
    if (x) irA({
      detail: x, bookingStep: "idle", bookingDay: null, bookingSlot: null, agenda: [], bookingFolio: null,
      bookingFechaLibre: "", bookingHoraLibre: "", agendaLibre: null,
    });
  },

  // Comparar
  "abrir-comparar": () => irA({ screen: "compare" }),
  "quitar-comparar": () => irA({ compare: [] }),
  "agendar-desde-comparar": (el) => {
    const x = medicoVisible(el.dataset.id);
    if (x) abrirAgenda(x);
  },

  // Ficha y agenda
  "cerrar-ficha": () => {
    soltarExpedienteDelDirectorio();
    irA({
      detail: null, bookingStep: "idle", agenda: [], bookingFolio: null,
      bookingFechaLibre: "", bookingHoraLibre: "", agendaLibre: null,
    });
  },
  "agendar": () => abrirAgenda(estado.detail),
  "volver-ficha": () => irA({ bookingStep: "idle" }),
  "confirmar-cita": confirmarCita,
  // Elegir una tarjeta de día o un horario sugerido deja sin efecto lo capturado a mano.
  "elegir-dia": (el) => irA({
    bookingDay: Number(el.dataset.indice), bookingSlot: null,
    bookingFechaLibre: "", bookingHoraLibre: "", agendaLibre: null,
  }),
  "elegir-horario": (el) => irA({ bookingSlot: el.dataset.valor, bookingHoraLibre: "" }),

  // Solicitudes (aprobar/rechazar/editar: solo Administrador, ver
  // _requerir_administrador en app/routers/solicitudes_alta_medico.py)
  "aprobar": (el) => cambiarEstatusSolicitud(Number(el.dataset.indice), "Aprobada"),
  "rechazar": (el) => cambiarEstatusSolicitud(Number(el.dataset.indice), "Rechazada"),
  "editar-solicitud": (el) => editarSolicitud(Number(el.dataset.indice)),

  // Alta de médico
  "enviar-alta": enviarAlta,
  "cancelar-edicion": cancelarEdicion,
  "registrar-otro": () => irA({ registered: null, ...sinEdicion() }),
  "hor-dia": alternarDia,
  "hor-agregar": agregarHorario,
  "hor-quitar": quitarHorario,
  "quitar-archivo-elegido": (el) => quitarArchivoElegido(el.dataset.tipo),
  "quitar-documento": (el) => quitarDocumentoGuardado(el.dataset.tipo),
  "ver-documento": (el) => verDocumento(el.dataset.folio, el.dataset.tipo),
};

/* ---------- Eventos (delegación) ---------- */
function alClic(e) {
  const enlaceVerificar = e.target.closest("[data-copiar]");
  if (enlaceVerificar) {
    // Sin preventDefault: el enlace abre el sitio oficial por sí solo.
    copiarParaVerificar(enlaceVerificar);
    return;
  }
  const el = e.target.closest("[data-accion]");
  // Casillas y combos se atienden en "change".
  if (!el || el.tagName === "INPUT" || el.tagName === "SELECT" || el.disabled) return;
  const accion = ACCIONES[el.dataset.accion];
  if (accion) accion(el);
}

function alCambiar(e) {
  const el = e.target;
  if (el.dataset.accion === "comparar") {
    const id = el.dataset.id;
    estado.compare = estado.compare.indexOf(id) >= 0
      ? estado.compare.filter(i => i !== id)
      : estado.compare.concat([id]).slice(-MAX_COMPARAR);
    pintar();
  } else if (el.dataset.filtro) {
    const llave = el.dataset.filtro;
    ponerFiltros({ [llave]: !estado.filters[llave] });
    pintar();
  } else if (el.id === "dp-orden") {
    ponerFiltros({ orden: el.value });
    pintar();
  } else if (el.type === "time" && el.dataset.hor) {
    cambiarHoraHorario(el);
  } else if (el.type === "file" && el.dataset.documento) {
    elegirDocumento(el);
  } else if (el.dataset.accionCambio === "elegir-especialidad-combo") {
    elegirEspecialidadDelCombo(el);
  } else if (el.tagName === "SELECT" && el.dataset.campoFuera) {
    cambiarComboFuera(el);
  } else if (el.tagName === "SELECT" && el.dataset.campo) {
    cambiarCombo(el);
  }
}

async function cambiarCombo(el) {
  const campo = el.dataset.campo;
  if (campo === "estado") {
    // Estado/Municipio del Alta de médico ya NO son el catálogo simulado de
    // Zona -- el municipio sale de dbo.sp_GetMun para la entidad elegida
    // (ver cargarMunicipiosAltaReal en datos.js), cacheado por entidad.
    // OJO: pintarDependientesAlta() NO toca #dp-mun-sel (solo la
    // verificación de cédula) -- hay que refrescarlo aquí a mano, antes
    // (estado "Cargando…") y después (ya con los municipios reales).
    ponerFormulario({ estado: el.value, municipio: "" });
    $("dp-mun-sel").innerHTML = V.opcionesMunicipio(V.calcular(estado));
    pintarDependientesAlta();
    await cargarMunicipiosAltaReal(el.value);
    $("dp-mun-sel").innerHTML = V.opcionesMunicipio(V.calcular(estado));
    pintarDependientesAlta();
  } else {
    ponerFormulario({ [campo]: el.value });
    pintarDependientesAlta();
  }
}

/* Buscador del paso "¿Para qué expediente?": solo se repinta la lista, para
   no perder el cursor del campo. */
function alEscribirFicha(e) {
  if (e.target.id !== "dp-exp-buscar") return;
  estado.expedienteBusqueda = e.target.value;
  const lista = document.getElementById("dp-exp-lista");
  if (lista) lista.innerHTML = V.listaExpedientesCita(V.calcular(estado));
}

/* Fecha y hora libres de la ficha (el modal vive fuera de #dp-raiz, por eso su
   propio "change"). Solo se guarda cuando el valor ya está completo: el campo de
   hora se arma por partes y repintar a cada tecla lo desharía. */
async function alCambiarFicha(e) {
  const el = e.target;
  if (el.id === "dp-fecha-libre") {
    const fecha = el.value;
    if (!fecha) {
      irA({ bookingFechaLibre: "", agendaLibre: null, bookingDay: 0, bookingSlot: null });
      return;
    }
    irA({ bookingFechaLibre: fecha, bookingDay: -1, agendaLibre: null, bookingSlot: null });
    const medico = estado.detail;
    if (!medico) return;
    const g = generacion;
    const dias = await cargarAgenda(medico.clave, fecha);
    if (g !== generacion || estado.bookingFechaLibre !== fecha) return;  // eligieron otra mientras tanto
    irA({ agendaLibre: dias[0] || null });
  } else if (el.id === "dp-hora-libre") {
    irA({ bookingHoraLibre: el.value, bookingSlot: null });
  }
}

function alEscribir(e) {
  const el = e.target;
  if (el.id === "dp-q") {
    estado.query = el.value;
    pintarSugerencias();
    return;
  }
  if (el.dataset.campoFuera) {
    // Solo se guarda el valor y se refresca el botón "Buscar": NO se
    // repinta toda la pantalla en cada tecla, para no perder el cursor.
    estado.fueraForm = { ...estado.fueraForm, [el.dataset.campoFuera]: el.value };
    pintarBotonFuera();
    return;
  }
  if (el.tagName !== "INPUT" || !el.dataset.campo) return;
  const campo = el.dataset.campo;
  if (RESTRICCIONES_ALTA[campo]) {
    // Solo los caracteres que la regla permite (también al pegar) y hasta su
    // máximo: RFC (13), cédula (8), teléfono (10), código postal (5), correo.
    const { limpiar, maximo } = RESTRICCIONES_ALTA[campo];
    const cursor = limpiar(el.value.slice(0, el.selectionStart || 0)).length;
    const limpio = limpiar(el.value).slice(0, maximo);
    if (limpio !== el.value) {
      el.value = limpio;
      try { el.setSelectionRange(Math.min(cursor, limpio.length), Math.min(cursor, limpio.length)); } catch (err) { /* no aplica */ }
    }
  }
  ponerFormulario({ [campo]: el.value });
  pintarDependientesAlta();
}

function alTeclear(e) {
  if (e.target.id === "dp-q" && e.key === "Enter") {
    e.preventDefault();
    buscar(estado.query);
    return;
  }
  if (e.target.dataset.campoFuera && e.key === "Enter") {
    e.preventDefault();
    buscarFuera();
  }
}

/* Habilita/deshabilita "Buscar" mientras se escribe la especialidad, sin
   repintar la pantalla completa. */
function pintarBotonFuera() {
  const boton = raiz.querySelector("[data-accion='buscar-fuera-de-red']");
  if (!boton) return;
  const v = V.calcular(estado);
  boton.disabled = !(v.fueraPuedeBuscar && !v.fueraBuscando);
  const nota = boton.parentElement.querySelector(".dp-nota");
  if (nota) {
    nota.textContent = v.fueraPuedeBuscar
      ? "Listo para buscar."
      : "Elige un estado y escribe al menos 3 caracteres de la especialidad.";
  }
}

/* ---------- Ciclo de vida de la pantalla ---------- */
export function montar(contenedor) {
  contenedor.innerHTML = PLANTILLA;
  raiz = $("dp-raiz");

  modalFicha = crearModal({
    id: "dp-ficha-modal",
    titulo: "",
    ancho: "600px",
    cuerpo: "",
    pie: "",
    // "X" del encabezado o clic fuera de la tarjeta: igual que "Cerrar".
    alCerrar: () => { soltarExpedienteDelDirectorio(); irA({ detail: null, bookingStep: "idle" }); },
  });
  modalFicha.elemento.querySelector(".modal-footer").classList.add("dp-ficha-pie");
  modalFicha.elemento.addEventListener("click", alClic);
  modalFicha.elemento.addEventListener("change", alCambiarFicha);
  modalFicha.elemento.addEventListener("input", alEscribirFicha);

  raiz.addEventListener("click", alClic);
  raiz.addEventListener("change", alCambiar);
  raiz.addEventListener("input", alEscribir);
  raiz.addEventListener("keydown", alTeclear);

  // Si se sale de la pantalla con la ficha abierta (ej. botón "atrás" del
  // navegador), la ficha no debe quedarse encima de otra pantalla.
  window.addEventListener("hashchange", () => {
    if (estado.detail && !location.hash.startsWith("#/directorio-proveedores")) modalFicha.cerrar();
    // Salir del directorio por otro camino (menú, "atrás") da por terminada la
    // coordinación: el aviso no debe quedarse esperando a un expediente.
    if (coordinacionActual() && !location.hash.startsWith("#/directorio-proveedores")) terminarCoordinacion();
  });

  estado.recent = leerRecientes();
  pintar();
}

export function alEntrar() {
  pintar();
  // El catálogo y las solicitudes pueden haber cambiado desde la última
  // visita (ej. Administrador cargó un catálogo nuevo, o aprobó una
  // solicitud) -- se vuelven a pedir cada vez que se entra a la pantalla.
  const catalogo = cargarCatalogoReal();
  catalogo.then(() => pintar());
  cargarSolicitudes();
  // Especialidades con su KPI (tarjetas + combo). Se vuelven a pedir cada
  // vez: los conteos cambian con cada carga de padrón o alta aprobada.
  olvidarEspecialidadesKpi();
  const especialidades = cargarEspecialidadesKpi();
  especialidades.then(() => pintar());
  // Viniendo de "Coordinar cita": la búsqueda se acomoda con los datos del
  // expediente, pero hasta que ya estén cargados el catálogo y las
  // especialidades (sin ellos no hay con qué emparejar).
  if (coordinacionActual()) {
    Promise.all([catalogo, especialidades]).then(() => aplicarCoordinacion());
  }
  // Catálogo de Entidad para el combo del Alta de médico -- se precarga al
  // entrar a la pantalla para que ya esté listo si el usuario navega a
  // "Alta de médico" (los municipios de la entidad elegida se piden aparte,
  // al cambiar el combo, ver cambiarCombo).
  cargarEntidadesAltaReal().then(() => pintar());
}

export function reiniciar() {
  // Al cerrar sesión se regresa todo al estado inicial (como recién abierto).
  generacion++;
  terminarCoordinacion();
  estado = estadoInicial();
  estado.recent = leerRecientes();
  pintar();
}
