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

/* Ventana de hasta 3 números de página alrededor de la actual (ej. en la
   página 7 de 24: 6, 7, 8), para saltar directo a una cercana sin tener que
   darle varias veces a Siguiente -- igual se recorre hacia los extremos si
   la actual ya está pegada al principio o al final. */
function ventanaDePaginas(pagina, totalPaginas) {
  const tam = Math.min(3, totalPaginas);
  let inicio = pagina - Math.floor(tam / 2);
  inicio = Math.max(1, Math.min(inicio, totalPaginas - tam + 1));
  return Array.from({ length: tam }, (_, i) => inicio + i);
}

/* alCambiar(nuevaPagina) se llama al presionar Anterior/Siguiente o un
   número de página.
   etiqueta: el sustantivo a mostrar ("expediente", "usuario", ...). */
export function renderPaginador(contenedor, { totalFilas, pagina, totalPaginas, alCambiar, etiqueta = "expediente" }) {
  if (!totalFilas) {
    contenedor.innerHTML = "";
    return;
  }
  const inicio = (pagina - 1) * FILAS_POR_PAGINA + 1;
  const fin = Math.min(pagina * FILAS_POR_PAGINA, totalFilas);
  const numeros = ventanaDePaginas(pagina, totalPaginas);
  contenedor.innerHTML = `
    <span class="pager-info">Mostrando ${inicio}–${fin} de ${totalFilas} ${etiqueta}${totalFilas === 1 ? "" : "s"}</span>
    <div class="pager-controls">
      <button class="btn btn-secondary" data-dir="-1" ${pagina <= 1 ? "disabled" : ""}>&larr; Anterior</button>
      <span class="pager-page">Página ${pagina} de ${totalPaginas}</span>
      <div class="pager-numeros">
        ${numeros.map(n => `<button type="button" class="pager-numero${n === pagina ? " activo" : ""}" data-pagina="${n}" ${n === pagina ? 'aria-current="page"' : ""}>${n}</button>`).join("")}
      </div>
      <button class="btn btn-secondary" data-dir="1" ${pagina >= totalPaginas ? "disabled" : ""}>Siguiente &rarr;</button>
    </div>
  `;
  contenedor.querySelectorAll("button[data-dir]").forEach(btn => {
    btn.addEventListener("click", () => alCambiar(pagina + parseInt(btn.dataset.dir, 10)));
  });
  contenedor.querySelectorAll("button[data-pagina]").forEach(btn => {
    btn.addEventListener("click", () => alCambiar(parseInt(btn.dataset.pagina, 10)));
  });
}
