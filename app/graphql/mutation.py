"""
Mutation root de GraphQL. Igual que query.py: reutiliza los mismos
repositorios y servicios que ya usa el REST -- en particular, las reglas
de autorización/flujo de trabajo de app/services/seguimiento_service.py,
app/services/estatus_service.py y accesos_repo.verificar_rol_administrador,
para que GraphQL nunca sea una puerta trasera que se salte lo que el REST
sí valida (ver PRs de seguridad: antes estas mutations solo exigían sesión
iniciada, sin importar el perfil ni las reglas de negocio).
"""

import strawberry
from fastapi import HTTPException

from app.core.rate_limit import verificar_limite
from app.core.security import crear_token
from app.graphql.inputs import (
    CuentaConfigInput,
    EnviarCorreoProveedoresInput,
    EstatusInput,
    LoginInput,
    SeguimientoInput,
)
from app.graphql.types import EnviarCorreoResultado, LoginResult, OperacionOk
from app.repositories import accesos_repo, auth_repo, cuentas_config_repo, estatus_repo, expedientes_repo
from app.routers.auth import MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS
from app.schemas.auth import LoginResponse
from app.schemas.correo import EnviarCorreoProveedoresResponse
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.services import email_service, estatus_service, seguimiento_service


def _elevar_error_graphql(e: HTTPException) -> Exception:
    """Las reglas compartidas con el REST lanzan HTTPException (status +
    detail); GraphQL no tiene ese concepto, así que se traduce al mismo
    patrón que ya usa este archivo para errores de negocio."""
    return Exception(e.detail)


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Pantalla de acceso. No requiere sesión previa.")
    def login(self, info: strawberry.Info, datos: LoginInput) -> LoginResult:
        ctx = info.context
        try:
            # Mismo límite que /auth/login (ver app/routers/auth.py): sin esto,
            # GraphQL era una puerta sin freno a fuerza bruta/credential
            # stuffing contra cuentas SISE.
            verificar_limite(
                f"login:{ctx.ip_cliente()}:{datos.usuario}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS
            )
            resultado = auth_repo.autenticar(
                datos.usuario, datos.password, ctx.host_servidor(), ctx.ip_cliente()
            )
        except auth_repo.UsuarioInactivo as e:
            raise Exception(str(e))
        except auth_repo.CredencialesInvalidas as e:
            raise Exception(str(e))
        except HTTPException as e:
            raise _elevar_error_graphql(e)

        token = crear_token(resultado["cl_usr_app"], resultado["usuario"], resultado["nombre"])
        return LoginResult.from_pydantic(
            LoginResponse(
                access_token=token,
                cl_usr_app=resultado["cl_usr_app"],
                usuario=resultado["usuario"],
                nombre=resultado["nombre"],
            )
        )

    @strawberry.mutation(description="Botón 'Actualizar en SISE'. Requiere sesión.")
    def actualizar_seguimiento(self, info: strawberry.Info, datos: SeguimientoInput) -> OperacionOk:
        usuario = info.context.requerir_usuario()
        try:
            seguimiento_service.actualizar_seguimiento(datos.cl_expediente, datos.comentario, usuario)
        except HTTPException as e:
            raise _elevar_error_graphql(e)
        return OperacionOk(ok=True, mensaje="Seguimiento registrado.")

    @strawberry.mutation(description="Cambia el estatus del expediente (solo en la app). Requiere sesión.")
    def actualizar_estatus(self, info: strawberry.Info, datos: EstatusInput) -> OperacionOk:
        usuario = info.context.requerir_usuario()
        try:
            resultado = estatus_service.actualizar_estatus(
                datos.cl_expediente, datos.estatus.value, usuario, datos.comentario
            )
        except HTTPException as e:
            raise _elevar_error_graphql(e)
        return OperacionOk(ok=True, mensaje=f"Estado actualizado a {resultado['estatus']}.")

    @strawberry.mutation(description="Botón 'Enviar correo a proveedores'. Requiere sesión.")
    def enviar_correo_proveedores(self, info: strawberry.Info, datos: EnviarCorreoProveedoresInput) -> EnviarCorreoResultado:
        usuario = info.context.requerir_usuario()
        if not datos.expedientes:
            raise Exception("Selecciona al menos un expediente antes de enviar el correo.")

        registros = []
        for cl_expediente in datos.expedientes:
            encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
            if encontrados:
                registros.append(encontrados[0])

        if not registros:
            raise Exception("No se encontró información de los expedientes seleccionados.")

        resultado = email_service.enviar_correo_proveedores(
            [r.model_dump() for r in registros],
            usuario_nombre=usuario.get("nombre") or usuario["usuario"],
        )

        # Paridad con el REST (ver routers/expedientes.py): mandar el correo
        # pasa el expediente a "En Espera de Respuesta" en automático.
        identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
        for r in registros:
            estatus_repo.actualizar_estatus(r.expediente, EstatusExpediente.EN_ESPERA_RESPUESTA, identificador)

        return EnviarCorreoResultado.from_pydantic(
            EnviarCorreoProveedoresResponse(enviados=resultado.enviados, expedientes=[r.expediente for r in registros])
        )

    @strawberry.mutation(description="Configuración Cuentas: agregar. Requiere sesión de Administrador.")
    def agregar_cuenta(self, info: strawberry.Info, datos: CuentaConfigInput) -> OperacionOk:
        usuario = info.context.requerir_usuario()
        try:
            accesos_repo.verificar_rol_administrador(usuario)
            cuentas_config_repo.agregar_cuenta_configurada(datos.cl_cuenta, datos.nombre)
        except ValueError as e:
            raise Exception(str(e))
        return OperacionOk(ok=True)

    @strawberry.mutation(description="Configuración Cuentas: eliminar una fila. Requiere sesión de Administrador.")
    def eliminar_cuenta(self, info: strawberry.Info, cl_cuenta: int) -> OperacionOk:
        usuario = info.context.requerir_usuario()
        try:
            accesos_repo.verificar_rol_administrador(usuario)
        except ValueError as e:
            raise Exception(str(e))
        eliminado = cuentas_config_repo.eliminar_cuenta_configurada(cl_cuenta)
        if not eliminado:
            raise Exception("Cuenta no encontrada en la configuración.")
        return OperacionOk(ok=True)

    @strawberry.mutation(description="Configuración Cuentas: botón 'Cancelar' (vacía el grid). Requiere sesión de Administrador.")
    def limpiar_cuentas_configuradas(self, info: strawberry.Info) -> OperacionOk:
        usuario = info.context.requerir_usuario()
        try:
            accesos_repo.verificar_rol_administrador(usuario)
        except ValueError as e:
            raise Exception(str(e))
        cuentas_config_repo.limpiar_cuentas_configuradas()
        return OperacionOk(ok=True, mensaje="Grid limpiado.")
