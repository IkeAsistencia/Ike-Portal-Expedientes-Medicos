/* Coordinar cita desde un expediente.

   El Proveedor está en Seguimiento, presiona "Coordinar cita" y pasa al
   Directorio de Proveedores. Este módulo es lo que recuerda, mientras tanto,
   DE QUÉ EXPEDIENTE viene y a dónde regresar: el directorio lo lee para abrir
   ya filtrado (especialidad, estado y municipio del expediente) y, al agendar,
   para devolverlo a Seguimiento con los datos de la cita copiados.

   Es solo memoria del navegador (no se guarda en ningún lado): si se recarga la
   página o se cierra sesión, la coordinación se da por terminada. */

let contexto = null;

/* record: el expediente tal como lo trae la lista (mismos campos que usa
   Seguimiento). fuente: cómo se abrió en Seguimiento ("link" o "menu"), para
   regresar exactamente a la misma vista. */
export function iniciarCoordinacion({ record, fuente }) {
  contexto = {
    record,
    fuente: fuente || "menu",
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
