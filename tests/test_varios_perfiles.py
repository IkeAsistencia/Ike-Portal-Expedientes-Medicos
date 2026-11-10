"""
Varios perfiles por RFC: una persona puede ser, por ejemplo, Administrador y
Cabina, con la misma contraseña, y elige con cuál entra en el login (ver
accesos_repo.agregar_perfil y _respuesta_de_sesion en app/routers/auth.py).
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.rate_limit import limpiar_todo
from app.main import app
from app.repositories import accesos_repo
from app.repositories.accesos_repo import PERFIL_ADMINISTRADOR, PERFIL_CABINA, PERFIL_PROVEEDOR

RFC = "ROCM940213"
PASSWORD = "Clave#2026"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "perfiles.db"))
    get_settings.cache_clear()

    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)
    limpiar_todo()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _persona_con_dos_perfiles():
    accesos_repo.alta_acceso(RFC, "Carlos Pineda", PERFIL_ADMINISTRADOR)
    accesos_repo.establecer_password(RFC, PASSWORD)
    accesos_repo.agregar_perfil(RFC, PERFIL_CABINA)


def _login(client, **extra):
    return client.post("/auth/rfc/login", json={"rfc": RFC, "password": PASSWORD, **extra})


def test_con_un_solo_perfil_entra_directo(client):
    accesos_repo.alta_acceso("MIMA991129", "Miranda", PERFIL_CABINA)
    accesos_repo.establecer_password("MIMA991129", PASSWORD)

    r = client.post("/auth/rfc/login", json={"rfc": "MIMA991129", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["perfil"] == PERFIL_CABINA
    assert r.json()["access_token"]


def test_con_varios_perfiles_pide_elegir_y_no_da_sesion(client):
    _persona_con_dos_perfiles()

    r = _login(client)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["requiere_perfil"] is True
    assert [p["perfil"] for p in cuerpo["perfiles"]] == [PERFIL_ADMINISTRADOR, PERFIL_CABINA]
    assert "access_token" not in cuerpo


def test_elegir_perfil_emite_la_sesion_con_ese_perfil(client):
    _persona_con_dos_perfiles()

    for elegido in (PERFIL_ADMINISTRADOR, PERFIL_CABINA):
        r = _login(client, perfil=elegido)
        assert r.status_code == 200, r.text
        assert r.json()["perfil"] == elegido
        # El token lleva ese perfil: el permiso real depende de él.
        cabecera = {"Authorization": f"Bearer {r.json()['access_token']}"}
        admin = client.get("/admin/accesos", headers=cabecera)
        assert (admin.status_code == 200) is (elegido == PERFIL_ADMINISTRADOR)


def test_no_se_puede_entrar_con_un_perfil_que_no_se_tiene(client):
    _persona_con_dos_perfiles()

    r = _login(client, perfil=PERFIL_PROVEEDOR)
    assert r.status_code == 403


def test_la_contrasena_se_valida_antes_de_ofrecer_perfiles(client):
    _persona_con_dos_perfiles()

    r = client.post("/auth/rfc/login", json={"rfc": RFC, "password": "Otra#2026x", "perfil": PERFIL_ADMINISTRADOR})
    assert r.status_code == 401


def test_crear_contrasena_con_varios_perfiles_pide_elegir(client):
    accesos_repo.alta_acceso(RFC, "Carlos Pineda", PERFIL_ADMINISTRADOR)
    accesos_repo.agregar_perfil(RFC, PERFIL_CABINA)

    r = client.post("/auth/rfc/crear-password", json={"rfc": RFC, "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["requiere_perfil"] is True
    # La contraseña quedó creada: ahora entra eligiendo perfil.
    assert _login(client, perfil=PERFIL_CABINA).json()["perfil"] == PERFIL_CABINA


def test_agregar_proveedor_exige_entidad_y_correo_y_lo_hace_proveedor(client):
    accesos_repo.alta_acceso(RFC, "Carlos Pineda", PERFIL_ADMINISTRADOR)

    with pytest.raises(accesos_repo.PerfilInvalido):
        accesos_repo.agregar_perfil(RFC, PERFIL_PROVEEDOR)

    accesos_repo.agregar_perfil(RFC, PERFIL_PROVEEDOR, "Jalisco", "prov@ikeasistencia.com")
    assert accesos_repo.buscar_acceso(RFC)["perfiles"] == [PERFIL_ADMINISTRADOR, PERFIL_PROVEEDOR]
    # Ya cuenta como Proveedor para el correo masivo y para cambiarle la entidad.
    assert {p["correo"] for p in accesos_repo.listar_proveedores_con_correo()} == {"prov@ikeasistencia.com"}
    assert accesos_repo.actualizar_entidad(RFC, "Campeche") is True


def test_no_se_repite_un_perfil_ni_se_agrega_a_un_rfc_inexistente(client):
    _persona_con_dos_perfiles()
    with pytest.raises(accesos_repo.PerfilYaAsignado):
        accesos_repo.agregar_perfil(RFC, PERFIL_CABINA)
    with pytest.raises(accesos_repo.AccesoNoEncontrado):
        accesos_repo.agregar_perfil("NADA000000", PERFIL_CABINA)


def test_quitar_perfil_y_limites(client):
    _persona_con_dos_perfiles()
    # Hay otro Administrador activo, para que quitar este no deje el portal sin uno.
    accesos_repo.alta_acceso("OTRO950101", "Otro Admin", PERFIL_ADMINISTRADOR)

    accesos_repo.quitar_perfil(RFC, PERFIL_ADMINISTRADOR)
    acceso = accesos_repo.buscar_acceso(RFC)
    assert acceso["perfiles"] == [PERFIL_CABINA]
    assert acceso["perfil"] == PERFIL_CABINA  # el principal pasó al que quedó

    with pytest.raises(accesos_repo.PerfilInvalido):  # su único perfil
        accesos_repo.quitar_perfil(RFC, PERFIL_CABINA)
    with pytest.raises(accesos_repo.PerfilInvalido):  # no lo tiene
        accesos_repo.quitar_perfil(RFC, PERFIL_PROVEEDOR)


def test_no_se_quita_el_ultimo_administrador_activo(client):
    _persona_con_dos_perfiles()

    with pytest.raises(accesos_repo.PerfilInvalido):
        accesos_repo.quitar_perfil(RFC, PERFIL_ADMINISTRADOR)
    assert PERFIL_ADMINISTRADOR in accesos_repo.buscar_acceso(RFC)["perfiles"]


def test_endpoints_de_administracion_de_perfiles(client):
    _persona_con_dos_perfiles()
    accesos_repo.alta_acceso("MIMA991129", "Miranda", PERFIL_CABINA)
    admin = {"Authorization": f"Bearer {_login(client, perfil=PERFIL_ADMINISTRADOR).json()['access_token']}"}

    # Un mismo RFC de 10 caracteres puede tener todos los perfiles.
    r = client.post("/admin/accesos/MIMA991129/perfiles", json={"perfil": PERFIL_ADMINISTRADOR}, headers=admin)
    assert r.status_code == 200, r.text

    r = client.post(
        "/admin/accesos/MIMA991129/perfiles",
        json={"perfil": PERFIL_PROVEEDOR, "entidad": "Jalisco", "correo": "m@ikeasistencia.com"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert client.post(
        "/admin/accesos/MIMA991129/perfiles",
        json={"perfil": PERFIL_PROVEEDOR, "entidad": "Jalisco", "correo": "m@ikeasistencia.com"},
        headers=admin,
    ).status_code == 409
    assert client.post("/admin/accesos/NADA000000/perfiles", json={"perfil": PERFIL_CABINA}, headers=admin).status_code == 404

    listado = {a["rfc"]: a for a in client.get("/admin/accesos", headers=admin).json()}
    assert listado["MIMA991129"]["perfiles"] == [PERFIL_ADMINISTRADOR, PERFIL_CABINA, PERFIL_PROVEEDOR]
    assert listado[RFC]["perfiles"] == [PERFIL_ADMINISTRADOR, PERFIL_CABINA]

    assert client.delete(f"/admin/accesos/MIMA991129/perfiles/{PERFIL_PROVEEDOR}", headers=admin).status_code == 200
    assert client.delete(f"/admin/accesos/MIMA991129/perfiles/{PERFIL_ADMINISTRADOR}", headers=admin).status_code == 200
    assert client.delete(f"/admin/accesos/MIMA991129/perfiles/{PERFIL_CABINA}", headers=admin).status_code == 400


def test_correo_del_proveedor_solo_de_la_empresa(client):
    _persona_con_dos_perfiles()
    accesos_repo.alta_acceso("MIMA991129", "Miranda", PERFIL_CABINA)
    admin = {"Authorization": f"Bearer {_login(client, perfil=PERFIL_ADMINISTRADOR).json()['access_token']}"}
    aviso = "El correo que acabas de ingresar no pertenece al dominio de @ikeasistencia.com."

    r = client.post(
        "/admin/accesos",
        json={"rfc": "PROV000001", "nombre": "Prov", "perfil": PERFIL_PROVEEDOR, "entidad": "Jalisco",
              "correo": "prov@gmail.com"},
        headers=admin,
    )
    assert r.status_code == 422
    assert aviso in r.text
    assert accesos_repo.buscar_acceso("PROV000001") is None

    r = client.post(
        "/admin/accesos/MIMA991129/perfiles",
        json={"perfil": PERFIL_PROVEEDOR, "entidad": "Jalisco", "correo": "m@ikeasistencia.com.mx"},
        headers=admin,
    )
    assert r.status_code == 422
    assert aviso in r.text
    assert accesos_repo.buscar_acceso("MIMA991129")["perfiles"] == [PERFIL_CABINA]


def test_la_migracion_pasa_el_perfil_de_los_accesos_viejos_a_la_lista(client, tmp_path):
    # Un acceso de antes (solo en usuarios_acceso, sin lista de perfiles).
    ruta = get_settings().local_db_path
    with sqlite3.connect(ruta) as conn:
        conn.execute(
            "INSERT INTO usuarios_acceso (rfc, nombre, perfil, entidad, correo) VALUES (?, ?, ?, 'NA', 'NA')",
            ("VIEJ900101", "Viejo", PERFIL_CABINA),
        )
        conn.execute("DELETE FROM usuarios_perfiles")

    from app.db.local_store import init_local_db

    init_local_db()
    assert accesos_repo.buscar_acceso("VIEJ900101")["perfiles"] == [PERFIL_CABINA]
