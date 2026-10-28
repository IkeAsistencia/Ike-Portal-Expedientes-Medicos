from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from app.core.security import usuario_actual
from app.repositories import (
    accesos_repo, comprobantes_repo, solicitudes_alta_documentos_repo, solicitudes_alta_medico_repo,
)
from app.repositories.accesos_repo import PERFIL_CABINA
from app.services import validacion_rfc_cedula_service as validacion


def _requerir_proveedor_o_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """Mismo criterio que app/routers/directorio_proveedores.py: "Alta de
    médico" vive dentro de la pantalla "Proveedores" (Proveedor y
    Administrador) -- Cabina no la usa."""
    if usuario.get("perfil") == PERFIL_CABINA:
        raise HTTPException(403, "Esta función no aplica para el perfil Cabina.")
    return usuario


def _requerir_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """
    Resolver una solicitud (aprobar/rechazar) y corregirla antes de
    resolverla son actos de REVISIÓN: solo Administrador (decisión del
    usuario, 2026-10-19). Cualquier perfil puede capturar su alta, pero
    nadie se aprueba a sí mismo -- aprobar inserta un proveedor real en el
    padrón, igual que la carga de Excel, que también es exclusiva de
    Administrador (ver app/routers/proveedores_catalogo.py).
    """
    try:
        accesos_repo.verificar_rol_administrador(usuario)
    except ValueError:
        raise HTTPException(
            403, "Revisar solicitudes de alta es exclusivo del perfil Administrador."
        )
    return usuario


router = APIRouter(
    prefix="/solicitudes-alta-medico",
    tags=["Directorio de Proveedores -- Alta de médico"],
    dependencies=[Depends(_requerir_proveedor_o_administrador)],
)


class SolicitudAltaInput(BaseModel):
    """
    Alta real de un médico en el portal. El domicilio va desglosado y es el
    del lugar DONDE DA LA CONSULTA (mismo criterio que la carga de Excel,
    ver app/services/proveedores_excel_service.py).
    """

    nombre: str = Field(min_length=1, max_length=150)
    especialidad: str = Field(min_length=1, max_length=100)
    # Todos los campos son obligatorios, salvo la cédula, el RFC y los
    # documentos (decisión del usuario, 2026-10-28): sin ellos la solicitud se
    # guarda igual, pero si se captura uno se revisa su formato. Su formato se
    # revisa en _validar_datos.
    cedula: str = Field(default="", max_length=20)
    rfc: str = Field(default="", max_length=20)
    estado: str = Field(min_length=1, max_length=60)
    municipio: str = Field(min_length=1, max_length=80)
    calle_num_ext_int: str = Field(min_length=1, max_length=180)
    colonia: str = Field(min_length=1, max_length=120)
    codigo_postal: str = Field(min_length=1, max_length=10)
    consultorio: str = Field(min_length=1, max_length=120)
    horario: str = Field(min_length=1, max_length=200)
    costo_consulta: str = Field(min_length=1, max_length=20)
    telefono: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=1, max_length=120)


class EstatusInput(BaseModel):
    estatus: str


def _validar_datos(data: SolicitudAltaInput) -> dict:
    """Todos los campos con valor y bien formados (ver
    validacion_rfc_cedula_service), menos la cédula y el RFC, que pueden ir
    vacíos pero, si traen algo, también se revisan. Se guardan ya
    normalizados: sin espacios de más, el RFC en mayúsculas y el teléfono solo
    con sus 10 dígitos. Sin cédula ni RFC se guarda "" (la columna cedula no
    admite NULL)."""
    try:
        return {
            **data.model_dump(),
            "nombre": validacion.exigir_texto(data.nombre, "El nombre"),
            "especialidad": validacion.exigir_texto(data.especialidad, "La especialidad"),
            "cedula": validacion.revisar_cedula(data.cedula) if data.cedula.strip() else "",
            "rfc": validacion.revisar_rfc(data.rfc).rfc if data.rfc.strip() else "",
            "estado": validacion.exigir_texto(data.estado, "El estado"),
            "municipio": validacion.exigir_texto(data.municipio, "El municipio"),
            "calle_num_ext_int": validacion.exigir_texto(data.calle_num_ext_int, "La calle y número"),
            "colonia": validacion.exigir_texto(data.colonia, "La colonia"),
            "codigo_postal": validacion.revisar_codigo_postal(data.codigo_postal),
            "consultorio": validacion.exigir_texto(data.consultorio, "El nombre del consultorio"),
            "horario": validacion.revisar_horario(data.horario),
            "costo_consulta": validacion.revisar_costo(data.costo_consulta),
            "telefono": validacion.revisar_telefono(data.telefono),
            "email": validacion.revisar_correo(data.email),
        }
    except validacion.DatoInvalido as e:
        raise HTTPException(400, str(e))


def _identificador(usuario: dict) -> str:
    return usuario.get("rfc") or usuario.get("usuario") or "desconocido"


def _exigir_que_no_se_repita(datos: dict, excluir_folio: str | None = None) -> None:
    """Un RFC puede tener varias altas, pero no la misma especialidad en el
    mismo domicilio (ver existe_alta_igual). El mensaje no dice de quién es la
    otra alta."""
    if solicitudes_alta_medico_repo.existe_alta_igual(datos, excluir_folio):
        raise HTTPException(
            409,
            "Ya existe un alta con este RFC y esta especialidad en ese mismo domicilio. "
            "Un RFC puede tener varias altas, pero con otra especialidad o en otro domicilio.",
        )


@router.get("")
def listar(usuario: dict = Depends(usuario_actual)):
    """Cada solicitud trae qué documentos se subieron (sin su contenido) y,
    solo para el Administrador, la revisión de su RFC (tipo de persona y si
    el dígito verificador cuadra): cómo se valida no se le muestra a quien
    captura."""
    documentos = solicitudes_alta_documentos_repo.resumen_por_folio()
    es_admin = _es_administrador(usuario)
    filas = []
    for s in solicitudes_alta_medico_repo.listar_solicitudes():
        fila = {**s, "documentos": documentos.get(s["folio"], {})}
        if es_admin:
            fila["rfc_revision"] = validacion.resumen_rfc(s.get("rfc"))
        filas.append(fila)
    return filas


@router.post("")
def crear(data: SolicitudAltaInput, usuario: dict = Depends(usuario_actual)):
    datos = _validar_datos(data)
    _exigir_que_no_se_repita(datos)
    return solicitudes_alta_medico_repo.crear_solicitud(datos, _identificador(usuario))


@router.put("/{folio}", dependencies=[Depends(_requerir_administrador)])
def editar(folio: str, data: SolicitudAltaInput):
    """
    Corrige los datos de una solicitud ANTES de resolverla (botón "Editar").
    Solo mientras siga "En revisión": una vez aprobada ya existe el
    proveedor en el padrón con su clave y sus citas, y una vez rechazada el
    expediente quedó cerrado -- en ninguno de los dos casos se edita desde
    aquí.
    """
    datos = _validar_datos(data)
    # Primero si existe y si todavía se puede editar: una ya aprobada choca
    # contra su propio renglón del padrón en la regla de duplicados, y el
    # mensaje correcto es que ya no se edita.
    actual = solicitudes_alta_medico_repo.obtener_solicitud(folio)
    if actual is None:
        raise HTTPException(404, "No se encontró esa solicitud.")
    if actual["estatus"] not in solicitudes_alta_medico_repo.ESTATUS_EDITABLES:
        raise HTTPException(
            409, f"La solicitud {folio} ya está {actual['estatus'].lower()}; sus datos ya no se pueden editar."
        )
    _exigir_que_no_se_repita(datos, excluir_folio=folio)
    try:
        solicitud = solicitudes_alta_medico_repo.actualizar_solicitud(folio, datos)
    except solicitudes_alta_medico_repo.SolicitudYaResuelta as e:
        raise HTTPException(409, str(e))
    if solicitud is None:
        raise HTTPException(404, "No se encontró esa solicitud.")
    return {"ok": True, "folio": folio}


@router.post("/{folio}/estatus", dependencies=[Depends(_requerir_administrador)])
def actualizar_estatus(folio: str, data: EstatusInput):
    """
    Aprobar da de alta al médico en el padrón con origen='portal' ("Alta
    rápida": sin el proceso formal de convenio con IKE) y le asigna su clave
    -- por eso se regresa `clave_proveedor`: es con la que ya se le pueden
    agendar citas.
    """
    if data.estatus not in solicitudes_alta_medico_repo.ESTATUS_VALIDOS:
        raise HTTPException(400, "Estatus inválido.")
    solicitud = solicitudes_alta_medico_repo.cambiar_estatus(folio, data.estatus)
    if solicitud is None:
        raise HTTPException(404, "No se encontró esa solicitud.")
    return {"ok": True, "clave_proveedor": solicitud.get("clave_proveedor")}


# ---------- Documentos opcionales (constancia de situación fiscal y cédula) ----------
# Los ve y los cambia solo el Administrador o quien capturó la solicitud: la
# constancia fiscal trae CURP y domicilio. Se cambian solo mientras la
# solicitud siga sin resolver; ya aprobada o rechazada quedan como evidencia.


def _es_administrador(usuario: dict) -> bool:
    try:
        accesos_repo.verificar_rol_administrador(usuario)
    except ValueError:
        return False
    return True


def _solicitud_con_documentos(folio: str, tipo: str, usuario: dict) -> dict:
    if tipo not in solicitudes_alta_documentos_repo.TIPOS_DOCUMENTO:
        raise HTTPException(404, "Ese tipo de documento no existe.")
    solicitud = solicitudes_alta_medico_repo.obtener_solicitud(folio)
    if solicitud is None:
        raise HTTPException(404, "No se encontró esa solicitud.")
    if not _es_administrador(usuario) and solicitud["rfc_solicito"] != _identificador(usuario):
        raise HTTPException(
            403, "Solo el Administrador o quien capturó la solicitud pueden ver o cambiar sus documentos."
        )
    return solicitud


def _exigir_editable(solicitud: dict) -> None:
    if solicitud["estatus"] not in solicitudes_alta_medico_repo.ESTATUS_EDITABLES:
        raise HTTPException(
            409, f"La solicitud ya está {solicitud['estatus'].lower()}; sus documentos ya no se pueden cambiar."
        )


def _nombre_seguro(nombre: str | None) -> str:
    # Solo el nombre, sin la ruta que algunos navegadores mandan completa.
    limpio = (nombre or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return limpio[:150] or "documento"


@router.post("/{folio}/documentos/{tipo}")
async def subir_documento(folio: str, tipo: str, archivo: UploadFile = File(...),
                          usuario: dict = Depends(usuario_actual)):
    solicitud = _solicitud_con_documentos(folio, tipo, usuario)
    _exigir_editable(solicitud)
    if archivo.content_type not in comprobantes_repo.TIPOS_MIME_PERMITIDOS:
        raise HTTPException(400, "Formato no permitido. Solo se aceptan PDF, JPG o PNG.")
    contenido = await archivo.read(comprobantes_repo.TAMANO_MAXIMO_BYTES + 1)
    if len(contenido) > comprobantes_repo.TAMANO_MAXIMO_BYTES:
        raise HTTPException(400, "El archivo supera el máximo permitido de 5 MB.")
    if not comprobantes_repo.contenido_coincide_con_tipo(contenido, archivo.content_type):
        raise HTTPException(400, "El contenido del archivo no corresponde al formato declarado (PDF, JPG o PNG).")
    documento = solicitudes_alta_documentos_repo.guardar(
        folio, tipo, _nombre_seguro(archivo.filename), archivo.content_type, contenido, _identificador(usuario),
    )
    return {"ok": True, "documento": documento}


@router.get("/{folio}/documentos/{tipo}")
def descargar_documento(folio: str, tipo: str, usuario: dict = Depends(usuario_actual)):
    _solicitud_con_documentos(folio, tipo, usuario)
    documento = solicitudes_alta_documentos_repo.obtener(folio, tipo)
    if documento is None:
        raise HTTPException(404, "Esta solicitud no tiene ese documento.")
    nombre = documento["nombre_archivo"]
    nombre_ascii = nombre.encode("ascii", "ignore").decode().replace('"', "") or "documento"
    return Response(
        content=documento["contenido"],
        media_type=documento["tipo_mime"],
        headers={"Content-Disposition": f"inline; filename=\"{nombre_ascii}\"; filename*=UTF-8''{quote(nombre)}"},
    )


@router.delete("/{folio}/documentos/{tipo}")
def quitar_documento(folio: str, tipo: str, usuario: dict = Depends(usuario_actual)):
    solicitud = _solicitud_con_documentos(folio, tipo, usuario)
    _exigir_editable(solicitud)
    if not solicitudes_alta_documentos_repo.quitar(folio, tipo):
        raise HTTPException(404, "Esta solicitud no tiene ese documento.")
    return {"ok": True}
