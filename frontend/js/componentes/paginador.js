/* Paginador "Mostrando X–Y de N · Anterior / Siguiente". */

export const FILAS_POR_PAGINA = 25;

/* Ajusta la página pedida al rango válido y regresa qué filas mostrar. */
export function paginar(rows, pagina) {
  const totalPaginas = Math.max(1, Math.ceil(rows.length / FILAS_POR_PAGINA));
  const paginaValida = Math.min(Math.max(pagina, 1), totalPaginas);
  const inicio = (paginaValida - 1) * FILAS_POR_PAGINA;
  return {
    pagina: paginaValida,
    totalPaginas,
    inicio,
    filas: rows.slice(inicio, inicio + FILAS_POR_PAGINA),
  };
}

/* alCambiar(nuevaPagina) se llama al presionar Anterior/Siguiente. */
export function renderPaginador(contenedor, { totalFilas, pagina, totalPaginas, alCambiar }) {
  if (!totalFilas) {
    contenedor.innerHTML = "";
    return;
  }
  const inicio = (pagina - 1) * FILAS_POR_PAGINA + 1;
  const fin = Math.min(pagina * FILAS_POR_PAGINA, totalFilas);
  contenedor.innerHTML = `
    <span class="pager-info">Mostrando ${inicio}–${fin} de ${totalFilas} expediente${totalFilas === 1 ? "" : "s"}</span>
    <div class="pager-controls">
      <button class="btn btn-secondary" data-dir="-1" ${pagina <= 1 ? "disabled" : ""}>&larr; Anterior</button>
      <span class="pager-page">Página ${pagina} de ${totalPaginas}</span>
      <button class="btn btn-secondary" data-dir="1" ${pagina >= totalPaginas ? "disabled" : ""}>Siguiente &rarr;</button>
    </div>
  `;
  contenedor.querySelectorAll("button[data-dir]").forEach(btn => {
    btn.addEventListener("click", () => alCambiar(pagina + parseInt(btn.dataset.dir, 10)));
  });
}
