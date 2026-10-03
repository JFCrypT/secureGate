import pytest

from app.config import ConfigError, load_env_file, load_settings
from tests.conftest import TEST_SECRET, TEST_TOKEN


def env(**overrides):
    values = {
        "SECUREGATE_API_URL": "http://127.0.0.1:8100/",
        "SECUREGATE_API_TOKEN": TEST_TOKEN,
        "FRONT_SESSION_SECRET": TEST_SECRET,
        "FRONT_OPERATORS_FILE": "operators.json",
    }
    values.update(overrides)
    return values


def test_valores_por_defecto():
    settings = load_settings(env())
    assert settings.api_url == "http://127.0.0.1:8100"
    assert settings.base_path == "/dashboard"
    assert settings.timezone == "America/Argentina/Buenos_Aires"
    assert settings.poll_realtime_ms == 2000
    assert settings.poll_status_ms == 5000
    assert settings.session_hours == 8


@pytest.mark.parametrize("name", ["SECUREGATE_API_TOKEN", "FRONT_SESSION_SECRET"])
@pytest.mark.parametrize("value", ["", "corto", "REEMPLAZAR_POR_TOKEN_DE_32_CARACTERES_O_MAS"])
def test_secretos_invalidos_no_arrancan_ni_se_imprimen(name, value):
    with pytest.raises(ConfigError) as error:
        load_settings(env(**{name: value}))
    assert name in str(error.value)
    if value:
        assert value not in str(error.value)


def test_el_error_no_muestra_el_token_valido():
    with pytest.raises(ConfigError) as error:
        load_settings(env(FRONT_TIMEZONE="Marte/Olimpo", FRONT_POLL_STATUS_MS="abc"))
    text = str(error.value)
    assert "FRONT_TIMEZONE" in text and "FRONT_POLL_STATUS_MS" in text
    assert TEST_TOKEN not in text and TEST_SECRET not in text


def test_repr_no_expone_secretos():
    text = repr(load_settings(env()))
    assert TEST_TOKEN not in text and TEST_SECRET not in text


@pytest.mark.parametrize("overrides", [
    {"SECUREGATE_API_URL": "127.0.0.1:8000"},
    {"FRONT_OPERATORS_FILE": ""},
    {"FRONT_BASE_PATH": "dashboard"},
    {"FRONT_SESSION_HOURS": "0"},
])
def test_valores_invalidos(overrides):
    with pytest.raises(ConfigError):
        load_settings(env(**overrides))


def test_env_file_no_pisa_el_entorno(tmp_path):
    path = tmp_path / ".env"
    path.write_text('# comentario\nA=1\nB="dos"\n\nC = tres\n', encoding="utf-8")
    environ = {"A": "ya-definida"}
    load_env_file(path, environ)
    assert environ == {"A": "ya-definida", "B": "dos", "C": "tres"}
