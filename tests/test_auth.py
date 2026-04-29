import contextvars
import os
import tempfile

import pytest
from pydantic import SecretStr

from oold.backend.auth import (
    BaseCredential,
    CertificateCredential,
    CredentialManager,
    OAuth1Credential,
    OAuth2Credential,
    TokenCredential,
    UserPwdCredential,
    dump_credentials,
    get_credential,
    load_credentials,
    set_credential,
)

# -- Basic set/get --


def test_set_and_get_credential():
    set_credential(
        UserPwdCredential(
            iri="localhost:8080", username="admin", password=SecretStr("pass123")
        )
    )
    cred = get_credential("localhost:8080")
    assert isinstance(cred, UserPwdCredential)
    assert cred.iri == "localhost:8080"
    assert cred.username == "admin"
    assert cred.password.get_secret_value() == "pass123"


def test_set_credential_with_token():
    set_credential(TokenCredential(iri="api.example.com", token=SecretStr("tok_abc")))
    cred = get_credential("api.example.com")
    assert isinstance(cred, TokenCredential)
    assert cred.token.get_secret_value() == "tok_abc"


def test_get_credential_missing_raises():
    with pytest.raises(ValueError, match="No credentials found"):
        get_credential("nonexistent.host:9999")


def test_overwrite_credential():
    set_credential(
        UserPwdCredential(
            iri="overwrite.test", username="user1", password=SecretStr("pass1")
        )
    )
    set_credential(
        UserPwdCredential(
            iri="overwrite.test", username="user2", password=SecretStr("pass2")
        )
    )
    cred = get_credential("overwrite.test")
    assert cred.username == "user2"


def test_contextvars_isolation():
    """Credentials set in a child context should not affect the parent."""
    set_credential(
        UserPwdCredential(
            iri="parent.test", username="parent_user", password=SecretStr("parent_pass")
        )
    )

    ctx = contextvars.copy_context()

    def child():
        set_credential(
            UserPwdCredential(
                iri="child.test",
                username="child_user",
                password=SecretStr("child_pass"),
            )
        )
        assert get_credential("child.test").username == "child_user"
        assert get_credential("parent.test").username == "parent_user"

    ctx.run(child)

    with pytest.raises(ValueError):
        get_credential("child.test")
    assert get_credential("parent.test").username == "parent_user"


# -- IRI matching --


def test_get_credential_exact_match():
    set_credential(
        UserPwdCredential(
            iri="match.exact.test", username="exact_user", password=SecretStr("p")
        )
    )
    cred = get_credential("match.exact.test", exact=True)
    assert cred.username == "exact_user"


def test_get_credential_exact_match_missing_raises():
    set_credential(
        UserPwdCredential(iri="match.exact.base", username="u", password=SecretStr("p"))
    )
    with pytest.raises(ValueError):
        get_credential("match.exact.base/subpath", exact=True)


def test_get_credential_substring_match():
    """Stored IRI is a substring of the search IRI."""
    set_credential(
        UserPwdCredential(
            iri="match.sub.host", username="sub_user", password=SecretStr("p")
        )
    )
    cred = get_credential("https://match.sub.host:443/api")
    assert cred.username == "sub_user"


def test_get_credential_most_specific_match():
    """Longest stored IRI that is a substring of the search wins."""
    set_credential(
        UserPwdCredential(
            iri="specificity.host", username="general", password=SecretStr("p")
        )
    )
    set_credential(
        UserPwdCredential(
            iri="specificity.host:443",
            username="port_specific",
            password=SecretStr("p"),
        )
    )
    set_credential(
        UserPwdCredential(
            iri="specificity.host:443/api",
            username="path_specific",
            password=SecretStr("p"),
        )
    )

    cred = get_credential("https://specificity.host:443/api/v2")
    assert cred.username == "path_specific"

    cred = get_credential("https://specificity.host:443/other")
    assert cred.username == "port_specific"

    cred = get_credential("https://specificity.host:8080/other")
    assert cred.username == "general"


def test_get_credential_no_substring_match_raises():
    set_credential(
        UserPwdCredential(iri="nomatch.host", username="u", password=SecretStr("p"))
    )
    with pytest.raises(ValueError):
        get_credential("completely.different.host")


# -- Credential class hierarchy --


def test_base_credential():
    cred = BaseCredential(iri="base.test")
    assert cred.iri == "base.test"


def test_user_pwd_credential():
    cred = UserPwdCredential(
        iri="u.test", username="admin", password=SecretStr("s3cret")
    )
    assert isinstance(cred, BaseCredential)
    assert cred.username == "admin"
    assert cred.password.get_secret_value() == "s3cret"


def test_user_pwd_credential_requires_fields():
    with pytest.raises(Exception):
        UserPwdCredential(iri="u.test")


def test_token_credential():
    cred = TokenCredential(iri="t.test", token=SecretStr("jwt_xyz"))
    assert isinstance(cred, BaseCredential)
    assert cred.token.get_secret_value() == "jwt_xyz"


def test_token_credential_requires_token():
    with pytest.raises(Exception):
        TokenCredential(iri="t.test")


def test_oauth1_credential():
    cred = OAuth1Credential(
        iri="o1.test",
        consumer_token="ct",
        consumer_secret=SecretStr("cs"),
        access_token="at",
        access_secret=SecretStr("as"),
    )
    assert isinstance(cred, BaseCredential)
    assert cred.consumer_token == "ct"
    assert cred.consumer_secret.get_secret_value() == "cs"


def test_oauth2_credential():
    cred = OAuth2Credential(
        iri="o2.test",
        access_token=SecretStr("access_tok"),
        refresh_token=SecretStr("refresh_tok"),
    )
    assert isinstance(cred, BaseCredential)
    assert cred.access_token.get_secret_value() == "access_tok"
    assert cred.token_type == "Bearer"


def test_oauth2_credential_minimal():
    cred = OAuth2Credential(iri="o2m.test", access_token=SecretStr("tok"))
    assert cred.refresh_token is None


def test_certificate_credential():
    cred = CertificateCredential(
        iri="cert.test",
        cert_path="/path/to/cert.pem",
        key_path="/path/to/key.pem",
        ca_path="/path/to/ca.pem",
    )
    assert isinstance(cred, BaseCredential)
    assert cred.cert_path == "/path/to/cert.pem"


def test_certificate_credential_minimal():
    cred = CertificateCredential(iri="certm.test", cert_path="/cert.pem")
    assert cred.key_path is None
    assert cred.ca_path is None


# -- set_credential preserves type --


def test_set_get_preserves_user_pwd_type():
    set_credential(
        UserPwdCredential(
            iri="db.example.com:5432", username="db_user", password=SecretStr("db_pass")
        )
    )
    retrieved = get_credential("db.example.com:5432")
    assert isinstance(retrieved, UserPwdCredential)


def test_set_get_preserves_oauth1_type():
    set_credential(
        OAuth1Credential(
            iri="wiki.typed.com",
            consumer_token="ct",
            consumer_secret=SecretStr("cs"),
            access_token="at",
            access_secret=SecretStr("as"),
        )
    )
    retrieved = get_credential("wiki.typed.com")
    assert isinstance(retrieved, OAuth1Credential)


def test_set_get_preserves_token_type():
    set_credential(
        TokenCredential(iri="postgrest.local:3000", token=SecretStr("pgrst_jwt"))
    )
    retrieved = get_credential("postgrest.local:3000")
    assert isinstance(retrieved, TokenCredential)


# -- IRI is part of credential --


def test_credential_iri_accessible():
    set_credential(
        UserPwdCredential(iri="iri.access.test", username="u", password=SecretStr("p"))
    )
    cred = get_credential("iri.access.test")
    assert cred.iri == "iri.access.test"


# -- YAML dump and load --


@pytest.fixture
def yaml_path():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_dump_and_load_user_pwd(yaml_path):
    creds = {
        "wiki.test.com": UserPwdCredential(
            iri="wiki.test.com", username="admin", password=SecretStr("secret")
        ),
    }
    dump_credentials(yaml_path, credentials=creds)

    loaded = load_credentials(yaml_path, into_store=False)
    assert "wiki.test.com" in loaded
    assert isinstance(loaded["wiki.test.com"], UserPwdCredential)
    assert loaded["wiki.test.com"].iri == "wiki.test.com"
    assert loaded["wiki.test.com"].username == "admin"
    assert loaded["wiki.test.com"].password.get_secret_value() == "secret"


def test_dump_and_load_token(yaml_path):
    creds = {
        "api.test.com": TokenCredential(iri="api.test.com", token=SecretStr("my_jwt")),
    }
    dump_credentials(yaml_path, credentials=creds)

    loaded = load_credentials(yaml_path, into_store=False)
    assert isinstance(loaded["api.test.com"], TokenCredential)
    assert loaded["api.test.com"].token.get_secret_value() == "my_jwt"


def test_dump_and_load_oauth1(yaml_path):
    creds = {
        "oauth.test.com": OAuth1Credential(
            iri="oauth.test.com",
            consumer_token="ct",
            consumer_secret=SecretStr("cs"),
            access_token="at",
            access_secret=SecretStr("as"),
        ),
    }
    dump_credentials(yaml_path, credentials=creds)

    loaded = load_credentials(yaml_path, into_store=False)
    assert isinstance(loaded["oauth.test.com"], OAuth1Credential)
    assert loaded["oauth.test.com"].consumer_token == "ct"


def test_dump_and_load_mixed(yaml_path):
    creds = {
        "wiki.mixed.com": UserPwdCredential(
            iri="wiki.mixed.com", username="u", password=SecretStr("p")
        ),
        "api.mixed.com": TokenCredential(iri="api.mixed.com", token=SecretStr("tok")),
        "cert.mixed.com": CertificateCredential(
            iri="cert.mixed.com", cert_path="/c.pem", key_path="/k.pem"
        ),
    }
    dump_credentials(yaml_path, credentials=creds)

    loaded = load_credentials(yaml_path, into_store=False)
    assert len(loaded) == 3
    assert isinstance(loaded["wiki.mixed.com"], UserPwdCredential)
    assert isinstance(loaded["api.mixed.com"], TokenCredential)
    assert isinstance(loaded["cert.mixed.com"], CertificateCredential)


def test_dump_excludes_iri_from_yaml(yaml_path):
    """IRI should be the YAML key, not repeated inside the value dict."""
    import yaml

    creds = {
        "iri.key.test": UserPwdCredential(
            iri="iri.key.test", username="u", password=SecretStr("p")
        ),
    }
    dump_credentials(yaml_path, credentials=creds)

    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    assert "iri" not in raw["iri.key.test"]
    assert raw["iri.key.test"]["username"] == "u"


def test_load_into_store(yaml_path):
    creds = {
        "store.load.test": UserPwdCredential(
            iri="store.load.test", username="loaded", password=SecretStr("pw")
        ),
    }
    dump_credentials(yaml_path, credentials=creds)

    ctx = contextvars.copy_context()

    def _check():
        load_credentials(yaml_path, into_store=True)
        cred = get_credential("store.load.test")
        assert cred.username == "loaded"
        assert cred.iri == "store.load.test"

    ctx.run(_check)


def test_dump_current_store(yaml_path):
    ctx = contextvars.copy_context()

    def _check():
        set_credential(TokenCredential(iri="dump.store.test", token=SecretStr("t")))
        dump_credentials(yaml_path)

        loaded = load_credentials(yaml_path, into_store=False)
        assert "dump.store.test" in loaded

    ctx.run(_check)


def test_load_osw_compatible_format(yaml_path):
    """YAML in the format used by osw CredentialManager."""
    import yaml

    data = {
        "wiki-dev.open-semantic-lab.org": {
            "username": "Simon Stier",
            "password": "stdPass@01",
        },
        "api.example.com": {
            "consumer_token": "ct",
            "consumer_secret": "cs",
            "access_token": "at",
            "access_secret": "as",
        },
    }
    with open(yaml_path, "w") as f:
        yaml.dump(data, f)

    loaded = load_credentials(yaml_path, into_store=False)
    wiki_cred = loaded["wiki-dev.open-semantic-lab.org"]
    assert isinstance(wiki_cred, UserPwdCredential)
    assert wiki_cred.iri == "wiki-dev.open-semantic-lab.org"
    assert wiki_cred.username == "Simon Stier"

    api_cred = loaded["api.example.com"]
    assert isinstance(api_cred, OAuth1Credential)
    assert api_cred.iri == "api.example.com"
    assert api_cred.consumer_token == "ct"


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_credentials("/nonexistent/path.yaml")


# CredentialManager tests


def test_credential_manager_single_file(yaml_path):
    """osw-compatible: single file, substring match."""
    import yaml

    data = {"test.domain.com": {"username": "testuser", "password": "pass123"}}
    with open(yaml_path, "w") as f:
        yaml.dump(data, f)

    cm = CredentialManager(cred_filepath=yaml_path)
    cred = cm.get_credential(CredentialManager.CredentialConfig(iri="domain.com"))
    assert cred is not None
    assert cred.username == "testuser"
    assert cred.password.get_secret_value() == "pass123"


def test_credential_manager_multi_file(yaml_path):
    import yaml

    data1 = {"test.domain.com": {"username": "u1", "password": "p1"}}
    data2 = {
        "test.domain.com:80": {"username": "u2", "password": "p2"},
        "domain.com:80": {"username": "u3", "password": "p3"},
    }
    path2 = yaml_path + ".2.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(data1, f)
    with open(path2, "w") as f:
        yaml.dump(data2, f)

    cm = CredentialManager(cred_filepath=[yaml_path, path2])
    cred = cm.get_credential(CredentialManager.CredentialConfig(iri="domain.com:80"))
    assert cred.username == "u3"

    os.unlink(path2)


def test_credential_manager_add_credential():
    cm = CredentialManager(cred_filepath=None)
    cred = UserPwdCredential(
        iri="added.test", username="added", password=SecretStr("pw")
    )
    cm.add_credential(cred)
    result = cm.get_credential(CredentialManager.CredentialConfig(iri="added.test"))
    assert result.username == "added"


def test_credential_manager_nested_types():
    """CredentialManager re-exports credential types as nested classes."""
    assert CredentialManager.BaseCredential is BaseCredential
    assert CredentialManager.UserPwdCredential is UserPwdCredential
    assert CredentialManager.OAuth1Credential is OAuth1Credential
