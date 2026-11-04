/* Login por RFC, en pasos: 1) RFC -> 2) crear contraseña (primera vez) o
   capturarla (ya existente).
   Si el portal aún no tiene ningún acceso, en vez de eso se muestra la
   activación inicial (RFC, nombre y contraseña) que crea al primer
   Administrador; ver /auth/activacion en app/routers/auth.py.
   Si el RFC tiene más de un perfil, después de la contraseña se pregunta
   "Entrar como" (paso "perfil"); para cambiar de perfil hay que cerrar sesión. */
import { api } from "../core/api.js";
import { guardarSesion, ultimoRfc } from "../core/sesion.js";
import { escapeHtml } from "../core/formato.js";
import { ICONOS } from "../componentes/iconos.js";

const PLANTILLA = `
  <div class="login-card">
    <img src="img/logo-ike-lema.png" alt="IKE · Mejoramos la vida de las personas" class="login-logo">
    <h1><img src="img/logo-atenea.png" alt="Equipo Atenea" class="marca-atenea-icono">Portal Promédico</h1>
    <p class="subtitle" id="login-subtitulo">Inicia sesión para continuar</p>
    <form id="login-form">
      <div class="field">
        <label for="login-rfc">RFC</label>
        <input type="text" id="login-rfc" maxlength="10" autocomplete="username" required>
        <a class="login-link hidden" id="login-cambiar-rfc" style="margin-top:6px;">Cambiar RFC</a>
      </div>

      <div class="field hidden" id="login-nombre-field">
        <label for="login-nombre">Nombre</label>
        <input type="text" id="login-nombre" maxlength="120" autocomplete="name">
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

      <div class="field hidden" id="login-perfil-field">
        <label for="login-perfil">Entrar como</label>
        <select id="login-perfil"></select>
      </div>

      <div class="hint hidden" id="login-nuevo-hint" style="margin:-8px 0 16px;">Es tu primera vez: crea una contraseña de al menos 8 caracteres, con mayúscula, minúscula, número y carácter especial (ej. !@#$%&*).</div>
      <div class="hint hidden" id="login-activacion-hint" style="margin:-8px 0 16px;">El portal aún no tiene usuarios. Quien se registre aquí queda como Administrador y desde ahí da de alta al resto. La contraseña debe tener al menos 8 caracteres, con mayúscula, minúscula, número y carácter especial (ej. !@#$%&*).</div>

      <div class="login-error" id="login-error"></div>
      <button type="submit" class="btn btn-primary btn-block" id="login-btn">Continuar</button>
    </form>
  </div>`;

const TEXTO_BOTON = {
  "rfc": "Continuar",
  "password": "Iniciar sesión",
  "crear-password": "Crear contraseña y entrar",
  "activacion": "Activar portal y entrar",
  "perfil": "Entrar",
};

const PATRON_RFC = /^[A-Z]{4}\d{6}$/;

let loginPaso = "rfc"; // "rfc" | "password" | "crear-password" | "activacion" | "perfil"
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

/* El RFC tiene varios perfiles: la contraseña ya quedó validada (o creada),
   falta elegir con cuál entra. La contraseña se queda en el campo (bloqueado)
   para repetir la petición con el perfil elegido. */
function mostrarPasoPerfil(perfiles) {
  loginPaso = "perfil";
  $("login-password").disabled = true;
  $("login-password-confirm").disabled = true;
  $("login-nuevo-hint").classList.add("hidden");
  $("login-perfil").innerHTML = perfiles
    .map(p => `<option value="${Number(p.perfil)}">${escapeHtml(p.nombre)}</option>`)
    .join("");
  $("login-perfil-field").classList.remove("hidden");
  $("login-perfil").focus();
}

function mostrarPasoActivacion() {
  loginPaso = "activacion";
  $("login-subtitulo").textContent = "Activación inicial del portal";
  $("login-nombre-field").classList.remove("hidden");
  $("login-password-field").classList.remove("hidden");
  $("login-password-confirm-field").classList.remove("hidden");
  $("login-activacion-hint").classList.remove("hidden");
  $("login-cambiar-rfc").classList.add("hidden");
  $("login-btn").textContent = TEXTO_BOTON.activacion;
  $("login-password").autocomplete = "new-password";
  $("login-rfc").focus();
}

export function mostrarPasoRfc() {
  loginPaso = "rfc";
  // También deshace la activación inicial: al cerrar sesión ya hay un
  // Administrador y el login vuelve a ser el normal.
  $("login-subtitulo").textContent = "Inicia sesión para continuar";
  $("login-nombre-field").classList.add("hidden");
  $("login-nombre").value = "";
  $("login-activacion-hint").classList.add("hidden");
  $("login-password").autocomplete = "current-password";
  $("login-perfil-field").classList.add("hidden");
  $("login-perfil").innerHTML = "";
  $("login-password").disabled = false;
  $("login-password-confirm").disabled = false;
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
    if (loginPaso === "activacion") {
      const nombre = $("login-nombre").value.trim();
      const password = $("login-password").value;
      if (!PATRON_RFC.test(rfc)) {
        errorEl.textContent = "El RFC debe tener 10 caracteres: 4 letras seguidas de 6 números (ej. ABCD123456).";
        return;
      }
      if (!nombre) {
        errorEl.textContent = "Captura tu nombre.";
        return;
      }
      if (!cumpleReglaPassword(password)) {
        errorEl.textContent = "La contraseña debe tener al menos 8 caracteres, con al menos una mayúscula, una minúscula, un número y un carácter especial (ej. !@#$%&*).";
        return;
      }
      if (password !== $("login-password-confirm").value) {
        errorEl.textContent = "Las contraseñas no coinciden.";
        return;
      }
      btn.textContent = "Activando…";
      const data = await api("/auth/activacion", { method: "POST", body: { rfc, nombre, password }, auth: false });
      guardarSesion(data, rfc);
      $("login-password").value = "";
      $("login-password-confirm").value = "";
      alIniciarSesion();
      return;
    }

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
    } else if (loginPaso === "perfil") {
      const perfil = Number($("login-perfil").value);
      data = await api("/auth/rfc/login", { method: "POST", body: { rfc, password, perfil }, auth: false });
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
    if (data.requiere_perfil) {
      mostrarPasoPerfil(data.perfiles);
      return;
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
export async function iniciar() {
  // Si el portal no tiene accesos todavía, lo primero es activarlo. Si la
  // consulta falla, se sigue con el login normal.
  try {
    const { requerida } = await api("/auth/activacion/estado", { auth: false });
    if (requerida) {
      mostrarPasoActivacion();
      return;
    }
  } catch {
    // sin respuesta: login normal
  }
  const rfc = ultimoRfc();
  if (rfc) {
    $("login-rfc").value = rfc;
    $("login-form").requestSubmit();
  } else {
    $("login-rfc").focus();
  }
}
