/* Validación de RFC y cédula profesional del "Alta de médico", para avisar
   MIENTRAS se escribe. Es la misma regla que aplica el servidor (ver
   app/services/validacion_rfc_cedula_service.py), que es quien manda: si
   cambian aquí, cambian allá.

   Solo se revisa que el dato esté bien formado. Para confirmar que existe,
   la pantalla ofrece ir al sitio oficial (SAT o SEP) con el dato copiado. */

export const URL_VALIDAR_RFC_SAT = "https://agsc.siat.sat.gob.mx/PTSC/ValidaRFC/index.jsf";
export const URL_CONSULTAR_CEDULA_SEP = "https://cedulaprofesional.sep.gob.mx/";

/* Documentos opcionales de la solicitud (mismos tipos que el servidor). */
export const DOCUMENTOS_ALTA = [
  { tipo: "constancia_fiscal", etiqueta: "Constancia de situación fiscal", corta: "Constancia fiscal", ayuda: "La emite el SAT." },
  { tipo: "cedula", etiqueta: "Cédula profesional", corta: "Cédula", ayuda: "La cédula electrónica de la SEP (PDF) o una foto o escaneo de la cédula." },
];
export const DOCUMENTO_TIPOS_PERMITIDOS = ["application/pdf", "image/jpeg", "image/png"];
export const DOCUMENTO_TAMANO_MAXIMO = 5 * 1024 * 1024; // 5 MB

const VALORES_DIGITO = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ Ñ";
const RFC_GENERICOS = ["XAXX010101000", "XEXX010101000"];
const PATRON = {
  fisica: /^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$/,
  moral: /^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$/,
};

export const normalizarRfc = (texto) => (texto || "").replace(/[\s-]/g, "").toUpperCase();

function digitoVerificador(rfc) {
  const base = rfc.slice(0, -1).padStart(12, " ");
  let suma = 0;
  for (let i = 0; i < 12; i++) suma += VALORES_DIGITO.indexOf(base[i]) * (13 - i);
  const r = 11 - (suma % 11);
  return r === 11 ? "0" : r === 10 ? "A" : String(r);
}

function fechaExiste(aammdd) {
  const aa = Number(aammdd.slice(0, 2)), mm = Number(aammdd.slice(2, 4)), dd = Number(aammdd.slice(4));
  return [1900, 2000].some(siglo => {
    const f = new Date(siglo + aa, mm - 1, dd);
    return f.getFullYear() === siglo + aa && f.getMonth() === mm - 1 && f.getDate() === dd;
  });
}

/* { estado: "vacio" | "invalido" | "valido", tipo: "fisica" | "moral" | null,
     digitoCorrecto, mensaje } */
export function revisarRfc(texto) {
  const rfc = normalizarRfc(texto);
  const invalido = (mensaje) => ({ estado: "invalido", tipo: null, digitoCorrecto: false, mensaje });
  if (!rfc) return { estado: "vacio", tipo: null, digitoCorrecto: false, mensaje: "El RFC es obligatorio." };
  if (RFC_GENERICOS.includes(rfc)) {
    return invalido("Ese es un RFC genérico del SAT (público en general o extranjero). Captura el RFC propio del médico o de su consultorio.");
  }
  const tipo = rfc.length === 13 ? "fisica" : rfc.length === 12 ? "moral" : null;
  if (!tipo) return invalido(`Debe tener 13 caracteres (persona física) o 12 (persona moral); tiene ${rfc.length}.`);
  const letras = tipo === "fisica" ? 4 : 3;
  if (!PATRON[tipo].test(rfc)) {
    return invalido(`El RFC de persona ${tipo === "fisica" ? "física" : "moral"} lleva ${letras} letras, 6 dígitos de fecha (AAMMDD) y 3 caracteres de homoclave.`);
  }
  const fecha = rfc.slice(letras, letras + 6);
  if (!fechaExiste(fecha)) return invalido(`La fecha del RFC (${fecha}) no existe: debe ser año, mes y día (AAMMDD).`);
  const digitoCorrecto = rfc.slice(-1) === digitoVerificador(rfc);
  return {
    estado: "valido", tipo, digitoCorrecto,
    mensaje: digitoCorrecto
      ? "Formato correcto."
      : "El formato es correcto, pero el dígito verificador no cuadra: confírmalo en el SAT.",
  };
}

export const etiquetaTipoRfc = (tipo) => tipo === "fisica" ? "Persona física" : tipo === "moral" ? "Persona moral" : "";

/* Campos del alta restringidos mientras se escribe: qué caracteres entran y
   cuántos. Es la misma regla que aplica el servidor. */
export const RESTRICCIONES_ALTA = {
  rfc: { limpiar: (t) => t.toUpperCase().replace(/[^A-ZÑ&0-9]/g, ""), maximo: 13 },
  cedula: { limpiar: (t) => t.replace(/\D/g, ""), maximo: 8 },
  phone: { limpiar: (t) => t.replace(/\D/g, ""), maximo: 10 },
  codigoPostal: { limpiar: (t) => t.replace(/\D/g, ""), maximo: 5 },
  email: { limpiar: (t) => t.replace(/\s/g, ""), maximo: 120 },
};

const CORREO = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$/;

/* ---------- Horario de atención ----------
   El selector maneja bloques { dias: [0..6], desde: "HH:MM", hasta: "HH:MM" }
   (0 = Lun). Se guarda como texto, igual que el Excel del padrón:
   "Lun-Vie 09:00-14:00; Sáb 09:00-13:00". El servidor revisa ese mismo formato. */
export const DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
export const bloqueHorarioVacio = () => ({ dias: [], desde: "", hasta: "" });

function textoDeDias(dias) {
  const orden = [...new Set(dias)].sort((a, b) => a - b);
  const seguidos = orden.every((d, i) => i === 0 || d === orden[i - 1] + 1);
  if (orden.length > 1 && seguidos) return `${DIAS_SEMANA[orden[0]]}-${DIAS_SEMANA[orden[orden.length - 1]]}`;
  return orden.map(d => DIAS_SEMANA[d]).join(", ");
}

/* Bloques → texto. Los bloques incompletos no se incluyen (revisarHorario los reporta). */
export function serializarHorario(bloques) {
  return (bloques || [])
    .filter(b => b.dias.length && b.desde && b.hasta)
    .map(b => `${textoDeDias(b.dias)} ${b.desde}-${b.hasta}`)
    .join("; ");
}

/* Texto → bloques, para editar una solicitud ya guardada. Si el texto no tiene
   el formato del selector (una solicitud vieja), regresa [] y se vuelve a capturar. */
export function parsearHorario(texto) {
  const bloques = [];
  for (const parte of (texto || "").split("; ")) {
    const m = parte.trim().match(/^(.+) (\d\d:\d\d)-(\d\d:\d\d)$/);
    if (!m) return [];
    const [, diasTxt, desde, hasta] = m;
    let dias;
    if (diasTxt.includes("-")) {
      const [a, b] = diasTxt.split("-").map(d => DIAS_SEMANA.indexOf(d));
      if (a < 0 || b < a) return [];
      dias = Array.from({ length: b - a + 1 }, (_, i) => a + i);
    } else {
      dias = diasTxt.split(", ").map(d => DIAS_SEMANA.indexOf(d));
      if (dias.some(d => d < 0)) return [];
    }
    bloques.push({ dias, desde, hasta });
  }
  return bloques;
}

/* null si el horario está bien; si no, el mensaje de lo que falta. */
export function revisarHorario(bloques) {
  if (!bloques || !bloques.length) return "Agrega al menos un horario de atención.";
  for (const b of bloques) {
    if (!b.dias.length) return "Elige los días de cada horario.";
    if (!b.desde || !b.hasta) return "Elige la hora de inicio y la de fin de cada horario.";
    if (b.desde >= b.hasta) return "La hora de inicio debe ser anterior a la de fin.";
  }
  return null;
}

/* Todos los campos del alta son obligatorios (solo los documentos son
   opcionales). Regresa [{ campo, etiqueta, mensaje }] con lo que falta o está
   mal; [] si todo está bien. `campo` es la llave del formulario. */
export function revisarFormularioAlta(f) {
  const faltas = [];
  const falta = (campo, etiqueta, mensaje) => faltas.push({ campo, etiqueta, mensaje: mensaje || `${etiqueta}: es obligatorio.` });
  const vacio = (v) => !String(v || "").trim();

  if (vacio(f.name)) falta("name", "Nombre completo");
  if (vacio(f.specialty)) falta("specialty", "Especialidad");
  if (vacio(f.consultorio)) falta("consultorio", "Nombre del consultorio");
  const fallaHorario = revisarHorario(f.horarioBloques);
  if (fallaHorario) falta("horario", "Horario de atención", "Horario de atención: " + fallaHorario);
  if (!cedulaConFormatoValido(f.cedula)) falta("cedula", "Cédula profesional", "Cédula profesional: debe tener 7 u 8 dígitos.");
  const rfc = revisarRfc(f.rfc);
  if (rfc.estado !== "valido") falta("rfc", "RFC", "RFC: " + rfc.mensaje);
  if (vacio(f.estado)) falta("estado", "Estado");
  if (vacio(f.municipio)) falta("municipio", "Municipio");
  if (vacio(f.calleNumExtInt)) falta("calleNumExtInt", "Calle y número");
  if (vacio(f.colonia)) falta("colonia", "Colonia");
  if (!/^\d{5}$/.test(f.codigoPostal || "")) falta("codigoPostal", "Código postal", "Código postal: debe tener 5 dígitos.");
  if (!/^\d{10}$/.test(f.phone || "")) falta("phone", "Teléfono", "Teléfono: debe tener 10 dígitos.");
  if (!CORREO.test((f.email || "").trim())) falta("email", "Correo electrónico", "Correo electrónico: debe tener un formato válido.");
  return faltas;
}

export function cedulaConFormatoValido(texto) {
  return /^\d{7,8}$/.test((texto || "").replace(/\s/g, ""));
}
