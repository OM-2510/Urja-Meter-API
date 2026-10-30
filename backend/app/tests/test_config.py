from app.config import _get_email


def test_email_setting_ignores_windows_username_and_reads_legacy_dotenv_key():
    assert _get_email({"USERNAME": "windows-user"}, {"USERNAME": "portal@example.com"}) == "portal@example.com"


def test_email_environment_variable_takes_precedence():
    assert _get_email(
        {"EMAIL": "environment@example.com"},
        {"EMAIL": "dotenv@example.com", "USERNAME": "legacy@example.com"},
    ) == "environment@example.com"
