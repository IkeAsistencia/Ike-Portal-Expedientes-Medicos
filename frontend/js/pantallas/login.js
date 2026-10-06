/* Login por RFC, en pasos: 1) RFC -> 2) crear contraseña (primera vez) o
   capturarla (ya existente). */
import { api } from "../core/api.js";
import { guardarSesion, ultimoRfc } from "../core/sesion.js";
import { ICONOS } from "../componentes/iconos.js";

const PLANTILLA = `
  <div class="login-card">
    <img src="img/logo-ike-lema.png" alt="IKE · Mejoramos la vida de las personas" class="login-logo">
    <h1>Portal Expedientes Médicos</h1>
    <p class="subtitle">Inicia sesión para continuar</p>
    <form id="login-form">
      <div class="field">
        <label for="login-rfc">RFC</label>
        <input type="text" id="login-rfc" maxlength="20" autocomplete="username" required>
        <a class="login-link hidden" id="login-cambiar-rfc" style="margin-top:6px;">Cambiar RFC</a>
      </div>

      <div class="field hidden" id="login-password-field">
        <label for="login-password">Contraseña</label>
        <div class="password-wrap">
          <input type="password" id="login-password" maxlength="40" autocomplete="current-password">
          <button type="button" class="password-toggle" id="login-password-toggle" title="Mostrar contraseña">
            ${ICONOS.ojo}
            ${ICONOS.ojoTachado}
          </button>
        </div>
      </div>

      <div class="field hidden" id="login-password-confirm-field">
        <label for="login-password-confirm">Confirma tu contraseña</label>
        <input type="password" id="login-password-confirm" maxlength="40" autocomplete="new-password">
      </div>

      <div class="hint hidden" id="login-nuevo-hint" style="margin:-8px 0 16px;">Es tu primera vez: crea una contraseña de al menos 8 caracteres, con mayúscula, minúscula, número y carácter especial (ej. !@#$%&*).</div>

      <div class="login-error" id="login-error"></div>
      <button type="submit" class="btn btn-primary btn-block" id="login-btn">Continuar</button>
    </form>
  </div>`;

const TEXTO_BOTON = {
  "rfc": "Continuar",
  "password": "Iniciar sesión",
  "crear-password": "Crear contraseña y entrar",
};

let loginPaso = "rfc"; // "rfc" | "password" | "crear-password"
let alIniciarSesion = () => {};

const $ = (id) => document.getElementById(id);

function cumpleReglaPassword(password) {
  return password.length >= 8 && /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password)
    && /[^A-Za-z0-9]/.test(password);
}

function mostrarPassword(mostrar) {
  const btn = $("login-password-toggle");
  $("login-password").type = mostrar ? "text" : "password";
  btn.querySelector(".icon-eye").classList.toggle("hidden", mostrar);
  btn.querySelector(".icon-eye-off").classList.toggle("hidden", !mostrar);
  btn.title = mostrar ? "Ocultar contraseña" : "Mostrar contraseña";
}

export function mostrarPasoRfc() {
  loginPaso = "rfc";
  $("login-password-field").classList.add("hidden");
  $("login-password-confirm-field").classList.add("hidden");
  $("login-nuevo-hint").classList.add("hidden");
  $("login-cambiar-rfc").classList.add("hidden");
  $("login-rfc").disabled = false;
  $("login-password").value = "";
  $("login-password-confirm").value = "";
  $("login-btn").textContent = TEXTO_BOTON.rfc;
  // Siempre regresa la contraseña a oculta (por si se dejó visible con el ícono de mostrar).
  mostrarPassword(false);
  $("login-rfc").focus();
}

async function enviarFormulario(e) {
  e.preventDefault();
  const rfc = $("login-rfc").value.trim().toUpperCase();
  const errorEl = $("login-error");
  errorEl.textContent = "";
  if (!rfc) return;
  if (loginPaso === "rfc" && rfc.length > 10) {
    errorEl.textContent = "El RFC no puede exceder 10 caracteres.";
    return;
  }

  const btn = $("login-btn");
  btn.disabled = true;

  try {
    if (loginPaso === "rfc") {
      btn.textContent = "Verificando…";
      const estado = await api("/auth/rfc/estado", { method: "POST", body: { rfc }, auth: false });
      if (!estado.autorizado) {
        errorEl.textContent = "Este RFC no está autorizado para usar el sistema.";
        return;
      }
      $("login-rfc").disabled = true;
      $("login-cambiar-rfc").classList.remove("hidden");
      $("login-password-field").classList.remove("hidden");
      if (estado.tiene_password) {
        loginPaso = "password";
      } else {
        loginPaso = "crear-password";
        $("login-password-confirm-field").classList.remove("hidden");
        $("login-nuevo-hint").classList.remove("hidden");
      }
      $("login-password").focus();
      return;
    }

    const password = $("login-password").value;
    let data;
    if (loginPaso === "password") {
      data = await api("/auth/rfc/login", { method: "POST", body: { rfc, password }, auth: false });
    } else {
      if (!cumpleReglaPassword(password)) {
        errorEl.textContent = "La contraseña debe tener al menos 8 caracteres, con al menos una mayúscula, una minúscula, un número y un carácter especial (ej. !@#$%&*).";
        return;
      }
      if (password !== $("login-password-confirm").value) {
        errorEl.textContent = "Las contraseñas no coinciden.";
        return;
      }
      data = await api("/auth/rfc/crear-password", { method: "POST", body: { rfc, password }, auth: false });
    }
    guardarSesion(data, rfc);
    $("login-password").value = "";
    $("login-password-confirm").value = "";
    alIniciarSesion();
  } catch (err) {
    errorEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = TEXTO_BOTON[loginPaso];
  }
}

/* alEntrar(): se llama cuando el login fue exitoso. */
export function montar(contenedor, { alEntrar }) {
  alIniciarSesion = alEntrar;
  contenedor.innerHTML = PLANTILLA;
  $("login-password-toggle").addEventListener("click", () => {
    mostrarPassword($("login-password").type === "password");
  });
  $("login-cambiar-rfc").addEventListener("click", mostrarPasoRfc);
  $("login-form").addEventListener("submit", enviarFormulario);
}

/* Si ya se había entrado antes en este navegador, precarga el RFC y salta
   directo al paso de contraseña. */
export function iniciar() {
  const rfc = ultimoRfc();
  if (rfc) {
    $("login-rfc").value = rfc;
    $("login-form").requestSubmit();
  } else {
    $("login-rfc").focus();
  }
}
