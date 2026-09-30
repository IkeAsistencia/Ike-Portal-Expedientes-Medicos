"""
Mutation root de GraphQL. Igual que query.py: reutiliza los mismos
repositorios y servicios que ya usa el REST.
"""

import strawberry

from app.core.security import crear_token
from app.graphql.inputs import (
    CuentaConfigInput,
    EnviarCorreoProveedoresInput,
    EstatusInput,
    LoginInput,
    SeguimientoInput,
)
from app.graphql.types import EnviarCorreoResultado, LoginResult, OperacionOk
from app.repositories import auth_repo, cuentas_config_repo, estatus_repo, expedientes_repo, seguimiento_repo
from app.schemas.auth import LoginResponse
from app.schemas.correo import EnviarCorreoProveedoresResponse
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.schemas.seguimiento import EstatusInput as EstatusInputPydantic
from app.schemas.seguimiento import SeguimientoInput as SeguimientoInputPydantic
from app.services import email_service


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Pantalla de acceso. No requiere sesión previa.")
    def login(self, info: strawberry.Info, datos: LoginInput) -> LoginResult:
        ctx = info.context
        try:
            resultado = auth_repo.autenticar(
                datos.usuario, datos.password, ctx.host_servidor(), ctx.ip_cliente()
            )
        except auth_repo.UsuarioInactivo as e:
            raise Exception(str(e))
        except auth_repo.CredencialesInvalidas as e:
            raise Exception(str(e))

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
        if not datos.comentario.strip():
            raise Exception("El comentario no puede estar vacío.")
        seguimiento_repo.registrar_seguimiento(
            SeguimientoInputPydantic(cl_expediente=datos.cl_expediente, comentario=datos.comentario),
            cl_usr_app=usuario["cl_usr_app"],
        )
        return OperacionOk(ok=True, mensaje="Seguimiento registrado.")

    @strawberry.mutation(description="Cambia el estatus del expediente (solo en la app). Requiere sesión.")
    def actualizar_estatus(self, info: strawberry.Info, datos: EstatusInput) -> OperacionOk:
        usuario = info.context.requerir_usuario()
        estatus = EstatusExpediente(datos.estatus.value)
        identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
        estatus_repo.actualizar_estatus(datos.cl_expediente, estatus, identificador)
        return OperacionOk(ok=True, mensaje=f"Estado actualizado a {estatus.value}.")

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

    @strawberry.mutation(description="Configuración Cuentas: agregar. Requiere sesión.")
    def agregar_cuenta(self, info: strawberry.Info, datos: CuentaConfigInput) -> OperacionOk:
        info.context.requerir_usuario()
        try:
            cuentas_config_repo.agregar_cuenta_configurada(datos.cl_cuenta, datos.nombre)
        except ValueError as e:
            raise Exception(str(e))
        return OperacionOk(ok=True)

    @strawberry.mutation(description="Configuración Cuentas: eliminar una fila. Requiere sesión.")
    def eliminar_cuenta(self, info: strawberry.Info, cl_cuenta: int) -> OperacionOk:
        info.context.requerir_usuario()
        eliminado = cuentas_config_repo.eliminar_cuenta_configurada(cl_cuenta)
        if not eliminado:
            raise Exception("Cuenta no encontrada en la configuración.")
        return OperacionOk(ok=True)

    @strawberry.mutation(description="Configuración Cuentas: botón 'Cancelar' (vacía el grid). Requiere sesión.")
    def limpiar_cuentas_configuradas(self, info: strawberry.Info) -> OperacionOk:
        info.context.requerir_usuario()
        cuentas_config_repo.limpiar_cuentas_configuradas()
        return OperacionOk(ok=True, mensaje="Grid limpiado.")
