/* Tarjeta de indicador (KPI): ícono + número + etiqueta. */

export function kpiHtml({ clase, idTarjeta, idIcono, idValor, idEtiqueta, etiqueta, icono, clicable = false, ocultaPorPerfil = false }) {
  const clases = ["kpi-card", clase, clicable ? "kpi-clickable" : "", ocultaPorPerfil ? "hidden-perfil" : ""].filter(Boolean).join(" ");
  return `
    <div class="${clases}"${idTarjeta ? ` id="${idTarjeta}"` : ""}${clicable ? ' title="Ver solo estos expedientes"' : ""}>
      <div class="kpi-icon"${idIcono ? ` id="${idIcono}"` : ""}>${icono}</div>
      <div class="kpi-info">
        <div class="kpi-value" id="${idValor}">0</div>
        <div class="kpi-label"${idEtiqueta ? ` id="${idEtiqueta}"` : ""}>${etiqueta}</div>
      </div>
    </div>`;
}
