/* Coordinar cita para un expediente (toda cita es para uno).

   Dos caminos: desde Seguimiento ("Coordinar cita" pasa al Directorio ya
   filtrado por la especialidad y zona del expediente), o desde el Directorio
   por el menú (al presionar "Agendar" se elige el expediente). Este módulo es
   lo que recuerda, mientras tanto, PARA QUÉ EXPEDIENTE es la cita: al
   agendar, el directorio regresa a Seguimiento de ese expediente con los
   datos de la cita copiados en Observaciones.

   Es solo memoria del navegador (no se guarda en ningún lado): si se recarga la
   página o se cierra sesión, la coordinación se da por terminada. */

let contexto = null;

/* record: el expediente tal como lo trae la lista (mismos campos que usa
   Seguimiento). fuente: cómo se abrió en Seguimiento ("link" o "menu"), para
   regresar exactamente a la misma vista. origen: dónde empezó la coordinación
   -- "seguimiento" (botón "Coordinar cita") o "directorio" (se eligió el
   expediente al presionar "Agendar"). Cancelar desde el directorio no lleva a
   ningún lado: solo suelta el expediente. */
export function iniciarCoordinacion({ record, fuente, origen }) {
  contexto = {
    record,
    fuente: fuente || "menu",
    origen: origen || "seguimiento",
    expediente: record.expediente,
    paciente: record.nombre_paciente || "",
    especialidad: record.especialidad || "",
    entidad: record.entidad || "",
    municipio: record.municipio || "",
  };
}

export function coordinacionActual() {
  return contexto;
}

/* Cierra la coordinación y regresa lo que se tenía (para volver al expediente). */
export function terminarCoordinacion() {
  const actual = contexto;
  contexto = null;
  return actual;
}
