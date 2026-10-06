/* Campo de número de expediente: solo dígitos y un máximo de caracteres.
   Se usa con <input type="text" inputmode="numeric"> (sin las flechas de
   type="number"; en celular abre el teclado numérico). */

export const DIGITOS_EXPEDIENTE = 10;

/* Limpia lo que se escriba o pegue (letras, espacios, signos) y corta al
   máximo. Sin maxlength a propósito: el navegador cortaría el texto pegado
   ANTES de quitar lo que no es número y se perderían dígitos. */
export function limitarADigitos(input, maximo = DIGITOS_EXPEDIENTE) {
  input.addEventListener("input", () => {
    const soloDigitos = input.value.replace(/\D/g, "").slice(0, maximo);
    if (soloDigitos !== input.value) input.value = soloDigitos;
  });
}
