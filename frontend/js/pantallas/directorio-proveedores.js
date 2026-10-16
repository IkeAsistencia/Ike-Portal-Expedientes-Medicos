/* Pantalla: Directorio de Proveedores (solo perfil Proveedor).
   Es la maqueta del prototipo "Directorio de Proveedores" (búsqueda de
   especialistas por zona y especialidad) metida dentro del portal: mismos
   textos, mismos datos simulados y mismo comportamiento que el original,
   con el diseño del portal. NO tiene conexión con el backend: no llama a la
   API ni toca expedientes, correos o usuarios; todo vive en el navegador.

   Sub-pantallas internas (por estado, no por hash): home, zone, results,
   compare, metrics, admin (Solicitudes) y register (Alta de médico), más la
   ficha/agenda del médico (modal) y la barra de comparar. Los datos y
   generadores están en js/directorio/datos.js y las plantillas en
   js/directorio/vistas.js. */
import { crearModal } from "../componentes/modal.js";
import {
  ESTADOS, RECENT_KEY, SEED_REQUESTS, PROPS,
  num, visible, formularioVacio, cargarCatalogoReal,
} from "../directorio/datos.js";
import * as V from "../directorio/vistas.js";

const PLANTILLA = `
  <div class="dp-directorio" id="dp-raiz">
    <div class="dp-barra" id="dp-barra"></div>
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
    query: "", searchTerm: null, recent: [],
    placesSynced: false, syncing: false,
    view: "list",
    filters: { maxPrice: 9999, hoy: false, tele: false, seguro: false, soloVerificados: false, orden: "rating" },
    compare: [],
    detail: null, bookingStep: "idle", bookingDay: null, bookingSlot: null,
    cedulaStatus: "idle", registered: null, requests: SEED_REQUESTS.slice(),
    form: formularioVacio(),
  };
}

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
  return [d.accion, d.valor, d.id, d.indice, d.filtro, d.campo].join("|");
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
function pintar() {
  if (!raiz) return;
  const foco = capturarFoco();
  const v = V.calcular(estado);

  $("dp-barra").innerHTML = V.barra(v);
  pintarPantalla(v);
  $("dp-pie").innerHTML = V.pie(v);

  const barraComparar = $("dp-barra-comparar");
  barraComparar.classList.toggle("hidden", !v.showCompareBar);
  barraComparar.innerHTML = v.showCompareBar ? V.barraComparar(v) : "";

  pintarFicha(v);
  restaurarFoco(foco);
  enviarMapa();
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
      price: d.price, rating: d.rating, fromPlaces: d.fromPlaces,
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
  $("dp-alta-panel").innerHTML = V.altaPanelCedula(v);
  $("dp-alta-nota").innerHTML = V.altaNota(v);
  restaurarFoco(foco);
}

/* ---------- Acciones (mismo efecto que los handlers del original) ---------- */
function irA(cambios) {
  Object.assign(estado, cambios);
  pintar();
}

function buscar(termino) {
  recordar(termino);
  irA({ screen: "results", searchTerm: termino, query: termino, specialty: null });
}

function sincronizarPlaces() {
  if (!PROPS.placesSync) return;
  if (estado.syncing || estado.placesSynced) return;
  irA({ syncing: true });
  const g = generacion;
  setTimeout(() => {
    if (g !== generacion) return;
    irA({ syncing: false, placesSynced: true });
  }, 1400);
}

function verificarCedula() {
  const c = (estado.form.cedula || "").trim();
  if (!/^\d{7,8}$/.test(c)) { irA({ cedulaStatus: "invalid" }); return; }
  irA({ cedulaStatus: "loading" });
  const g = generacion;
  setTimeout(() => {
    if (g !== generacion) return;
    irA({ cedulaStatus: "valid" });
  }, 1200);
}

function enviarAlta() {
  if (estado.cedulaStatus !== "valid") { irA({ cedulaStatus: "invalid" }); return; }
  const fm = estado.form;
  const folio = "ALT-" + num(fm.cedula, "f", 10000, 99999);
  irA({
    registered: { name: fm.name || "El médico", folio },
    requests: [{ folio, name: fm.name || "Solicitante sin nombre", specialty: fm.specialty, zone: fm.municipio + ", " + fm.estado, cedula: fm.cedula, rfc: fm.rfc || "—", status: "En revisión" }].concat(estado.requests),
  });
}

function cambiarEstatusSolicitud(indice, estatus) {
  irA({ requests: estado.requests.map((x, j) => (j === indice ? Object.assign({}, x, { status: estatus }) : x)) });
}

const medicoVisible = (id) => visible(estado).find(x => x.id === id) || null;

const ACCIONES = {
  // Barra propia y "volver"
  "ir-inicio": () => irA({ screen: "home", searchTerm: null, detail: null }),
  "ir-metricas": () => irA({ screen: "metrics", detail: null }),
  "ir-solicitudes": () => irA({ screen: "admin", detail: null }),
  "ir-alta": () => irA({ screen: "register", detail: null }),
  "volver-zona": () => irA({ screen: estado.searchTerm ? "home" : "zone", searchTerm: null }),
  "volver-resultados": () => irA({ screen: "results" }),

  // Inicio y zona
  "buscar": () => buscar(estado.query),
  "buscar-termino": (el) => buscar(el.dataset.valor),
  "sincronizar": sincronizarPlaces,
  "elegir-especialidad": (el) => irA({ screen: "zone", specialty: el.dataset.valor, estado: null, municipio: null, searchTerm: null }),
  "elegir-estado": (el) => irA({ estado: el.dataset.valor, municipio: null }),
  "elegir-municipio": (el) => irA({ screen: "results", municipio: el.dataset.valor, searchTerm: null }),

  // Resultados
  "vista-lista": () => irA({ view: "list" }),
  "vista-mapa": () => irA({ view: "map" }),
  "precio": (el) => { ponerFiltros({ maxPrice: Number(el.dataset.valor) }); pintar(); },
  "limpiar-filtros": () => { ponerFiltros({ maxPrice: 9999, hoy: false, tele: false, seguro: false, soloVerificados: false }); pintar(); },
  "ficha": (el) => {
    const x = medicoVisible(el.dataset.id);
    if (x) irA({ detail: x, bookingStep: "idle", bookingDay: null, bookingSlot: null });
  },

  // Comparar
  "abrir-comparar": () => irA({ screen: "compare" }),
  "quitar-comparar": () => irA({ compare: [] }),
  "agendar-desde-comparar": (el) => {
    const x = medicoVisible(el.dataset.id);
    if (x) irA({ detail: x, bookingStep: "pick", bookingDay: 0, bookingSlot: null });
  },

  // Ficha y agenda
  "cerrar-ficha": () => irA({ detail: null, bookingStep: "idle" }),
  "agendar": () => irA({ bookingStep: "pick", bookingDay: 0, bookingSlot: null }),
  "volver-ficha": () => irA({ bookingStep: "idle" }),
  "confirmar-cita": () => { if (estado.bookingSlot) irA({ bookingStep: "done" }); },
  "elegir-dia": (el) => irA({ bookingDay: Number(el.dataset.indice), bookingSlot: null }),
  "elegir-horario": (el) => irA({ bookingSlot: el.dataset.valor }),

  // Solicitudes
  "aprobar": (el) => cambiarEstatusSolicitud(Number(el.dataset.indice), "Aprobada"),
  "rechazar": (el) => cambiarEstatusSolicitud(Number(el.dataset.indice), "Rechazada"),

  // Alta de médico
  "verificar-cedula": verificarCedula,
  "enviar-alta": enviarAlta,
  "registrar-otro": () => irA({ registered: null, cedulaStatus: "idle", form: formularioVacio() }),
};

/* ---------- Eventos (delegación) ---------- */
function alClic(e) {
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
  } else if (el.tagName === "SELECT" && el.dataset.campo) {
    cambiarCombo(el);
  }
}

function cambiarCombo(el) {
  const campo = el.dataset.campo;
  if (campo === "estado") {
    const est = ESTADOS.find(x => x.name === el.value);
    ponerFormulario({ estado: el.value, municipio: est.municipios[0] });
    $("dp-mun-sel").innerHTML = V.opcionesMunicipio(V.calcular(estado));
  } else {
    ponerFormulario({ [campo]: el.value });
  }
  pintarDependientesAlta();
}

function alEscribir(e) {
  const el = e.target;
  if (el.id === "dp-q") {
    estado.query = el.value;
    pintarSugerencias();
    return;
  }
  if (el.tagName !== "INPUT" || !el.dataset.campo) return;
  const campo = el.dataset.campo;
  if (campo === "rfc") {
    // El RFC se guarda en mayúsculas (igual que el original), sin mover el cursor.
    const inicio = el.selectionStart, fin = el.selectionEnd;
    el.value = el.value.toUpperCase();
    try { el.setSelectionRange(inicio, fin); } catch (err) { /* no aplica */ }
  }
  ponerFormulario({ [campo]: el.value });
  // Cambiar la cédula invalida la verificación anterior.
  if (campo === "cedula") estado.cedulaStatus = "idle";
  pintarDependientesAlta();
}

function alTeclear(e) {
  if (e.target.id === "dp-q" && e.key === "Enter") {
    e.preventDefault();
    buscar(estado.query);
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
    alCerrar: () => irA({ detail: null, bookingStep: "idle" }),
  });
  modalFicha.elemento.querySelector(".modal-footer").classList.add("dp-ficha-pie");
  modalFicha.elemento.addEventListener("click", alClic);

  raiz.addEventListener("click", alClic);
  raiz.addEventListener("change", alCambiar);
  raiz.addEventListener("input", alEscribir);
  raiz.addEventListener("keydown", alTeclear);

  // Si se sale de la pantalla con la ficha abierta (ej. botón "atrás" del
  // navegador), la ficha no debe quedarse encima de otra pantalla.
  window.addEventListener("hashchange", () => {
    if (estado.detail && !location.hash.startsWith("#/directorio-proveedores")) modalFicha.cerrar();
  });

  estado.recent = leerRecientes();
  pintar();
}

export function alEntrar() {
  pintar();
  // El catálogo real puede haber cambiado desde la última visita (ej.
  // Administrador cargó uno nuevo) -- se vuelve a pedir cada vez que se
  // entra a la pantalla, y se repinta si ya había una búsqueda en curso.
  cargarCatalogoReal().then(() => pintar());
}

export function reiniciar() {
  // Al cerrar sesión se regresa todo al estado inicial (como recién abierto).
  generacion++;
  estado = estadoInicial();
  estado.recent = leerRecientes();
  pintar();
}
