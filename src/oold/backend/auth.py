import contextvars
import getpass
import logging
from enum import Enum
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Union

from pydantic import BaseModel, SecretStr

_logger = logging.getLogger(__name__)


# Credential types


class BaseCredential(BaseModel):
    """Abstract base class for credentials."""

    iri: str
    """The IRI this credential is valid for."""


class UserPwdCredential(BaseCredential):
    """Username and password authentication."""

    username: str
    password: SecretStr


class TokenCredential(BaseCredential):
    """Bearer token authentication (API keys, JWTs, etc.)."""

    token: SecretStr


class OAuth1Credential(BaseCredential):
    """OAuth1 credentials.

    See https://requests-oauthlib.readthedocs.io/en/latest/oauth1_workflow.html
    """

    consumer_token: str
    consumer_secret: SecretStr
    access_token: str
    access_secret: SecretStr


class OAuth2Credential(BaseCredential):
    """OAuth2 credentials with access and optional refresh token."""

    access_token: SecretStr
    refresh_token: Optional[SecretStr] = None
    token_type: str = "Bearer"


class CertificateCredential(BaseCredential):
    """TLS client certificate authentication."""

    cert_path: str
    key_path: Optional[str] = None
    ca_path: Optional[str] = None


# Registry for credential type inference from YAML fields

# Ordered most-specific-first so the first full match wins
_CREDENTIAL_TYPES: List[type] = [
    OAuth1Credential,
    OAuth2Credential,
    CertificateCredential,
    UserPwdCredential,
    TokenCredential,
]

_BASE_FIELDS = {"iri"}


def _infer_credential_type(data: dict) -> type:
    """Infer the most specific credential class from a dict of fields."""
    for cls in _CREDENTIAL_TYPES:
        required = {
            name
            for name, field in cls.model_fields.items()
            if field.is_required() and name not in _BASE_FIELDS
        }
        if required <= data.keys():
            return cls
    return BaseCredential


# Context-var credential store

_credentials: contextvars.ContextVar[
    Dict[str, BaseCredential]
] = contextvars.ContextVar("oold_credentials", default={})


def set_credential(credential: BaseCredential):
    """Store a credential. The credential's ``iri`` field is used as the key."""
    creds = _credentials.get().copy()
    creds[credential.iri] = credential
    _credentials.set(creds)


def get_credential(iri: str, exact: bool = False) -> BaseCredential:
    """Retrieve the credential for the given IRI from the global store.

    Parameters
    ----------
    iri
        The IRI to look up.
    exact
        If True, only exact key matches are returned.
    """
    creds = _credentials.get()
    cred = find_credential(iri, creds, exact=exact)
    if cred is None:
        raise ValueError(f"No credentials found for {iri}")
    return cred


# IRI matching


def find_credential(
    iri: str,
    credentials: Dict[str, BaseCredential],
    exact: bool = False,
) -> Optional[BaseCredential]:
    """Find the best matching credential for the given IRI.

    Matching strategy (when ``exact=False``):

    1. **Exact match** - IRI equals a stored key.

    2. **Stored-in-search** (most specific wins) - a stored IRI is a
       substring of the search IRI. The longest stored IRI wins.
       Use case: controller has a full URL, finds the best credential.
       Example: search ``"https://wiki.example.com:443/api"`` matches
       stored ``"wiki.example.com:443/api"`` over ``"wiki.example.com"``.

    3. **Search-in-stored** (broadest wins) - the search IRI is a
       substring of a stored IRI. The shortest stored IRI wins.
       Use case: user remembers a domain fragment, finds the credential.
       Example: search ``"domain.com"`` matches stored ``"test.domain.com"``.

    Step 2 is tried before step 3 because a specific credential that
    covers the full URL is a stronger match than a broad key that
    happens to contain the search term.

    Parameters
    ----------
    iri
        The IRI to search for.
    credentials
        Dict of stored IRI to BaseCredential.
    exact
        If True, only exact key matches are returned.
    """
    # 1. Exact match
    if iri in credentials:
        return credentials[iri]

    if exact:
        return None

    # 2. Stored IRI is substring of search IRI (longest/most-specific wins)
    best_len = 0
    best_cred = None
    for stored_iri, cred in credentials.items():
        if stored_iri in iri and len(stored_iri) > best_len:
            best_len = len(stored_iri)
            best_cred = cred
    if best_cred is not None:
        return best_cred

    # 3. Search IRI is substring of stored IRI (shortest/broadest wins)
    best_len = 0
    best_cred = None
    for stored_iri, cred in credentials.items():
        if iri in stored_iri:
            if best_len == 0 or len(stored_iri) < best_len:
                best_len = len(stored_iri)
                best_cred = cred
    return best_cred


# YAML persistence


def _secret_value(v) -> str:
    """Extract plain string from a SecretStr or pass through."""
    if isinstance(v, SecretStr):
        return v.get_secret_value()
    return v


def dump_credentials(
    filepath: Union[str, Path],
    credentials: Optional[Dict[str, BaseCredential]] = None,
):
    """Save credentials to a YAML file.

    Format::

        wiki.example.com:
          username: admin
          password: secret
        api.example.com:
          token: jwt_xyz

    The ``iri`` field is used as the YAML key and excluded from the value dict.

    Parameters
    ----------
    filepath
        Path to write the YAML file.
    credentials
        Dict of IRI to BaseCredential. If None, dumps the current context-var store.
    """
    import yaml

    if credentials is None:
        credentials = _credentials.get()

    data = {}
    for iri, cred in credentials.items():
        entry = {}
        for name, value in cred.model_dump().items():
            if name == "iri" or value is None:
                continue
            entry[name] = _secret_value(value)
        data[iri] = entry

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def load_credentials(
    filepath: Union[str, Path],
    into_store: bool = True,
) -> Dict[str, BaseCredential]:
    """Load credentials from a YAML file.

    The credential type is inferred from the fields present in each entry
    (e.g. ``username`` + ``password`` produces a ``UserPwdCredential``).
    The YAML key becomes the ``iri`` field.

    Parameters
    ----------
    filepath
        Path to the YAML file.
    into_store
        If True, loaded credentials are also stored into the context-var store.

    Returns
    -------
    dict
        IRI to BaseCredential mapping.
    """
    import yaml

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Credentials file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return {}

    result: Dict[str, BaseCredential] = {}
    for iri, fields in raw.items():
        if not isinstance(fields, dict):
            continue
        cls = _infer_credential_type(fields)
        coerced = {"iri": iri}
        for key, value in fields.items():
            field_info = cls.model_fields.get(key)
            if field_info and field_info.annotation in (
                SecretStr,
                Optional[SecretStr],
            ):
                coerced[key] = (
                    SecretStr(value) if not isinstance(value, SecretStr) else value
                )
            else:
                coerced[key] = value
        result[iri] = cls(**coerced)

    if into_store:
        creds = _credentials.get().copy()
        creds.update(result)
        _credentials.set(creds)

    return result


# CredentialManager


class CredentialManager(BaseModel):
    """Manages credentials from YAML files and the global in-memory store.

    Compatible with osw.auth.CredentialManager API.
    """

    cred_filepath: Optional[Union[Union[str, Path], List[Union[str, Path]]]] = None
    """Filepath(s) to YAML file(s) with credentials."""

    class CredentialFallback(str, Enum):
        ask = "ask"
        none = "none"

    class CredentialConfig(BaseModel):
        iri: str
        """IRI to look up."""
        fallback: Optional[str] = "none"
        """Fallback strategy if no credential found: 'ask' or 'none'."""

    # Re-export credential types as nested classes for osw compatibility
    BaseCredential: ClassVar[type] = BaseCredential
    UserPwdCredential: ClassVar[type] = UserPwdCredential
    TokenCredential: ClassVar[type] = TokenCredential
    OAuth1Credential: ClassVar[type] = OAuth1Credential
    OAuth2Credential: ClassVar[type] = OAuth2Credential
    CertificateCredential: ClassVar[type] = CertificateCredential

    def model_post_init(self, __context):
        if self.cred_filepath is not None:
            if not isinstance(self.cred_filepath, list):
                self.cred_filepath = [self.cred_filepath]
            self.cred_filepath = [Path(fp) for fp in self.cred_filepath if fp != ""]

    def _load_file_credentials(self) -> Dict[str, BaseCredential]:
        """Load credentials from all configured YAML files."""
        result: Dict[str, BaseCredential] = {}
        if not self.cred_filepath:
            return result
        for fp in self.cred_filepath:
            fp = Path(fp)
            if not fp.exists():
                continue
            try:
                loaded = load_credentials(fp, into_store=False)
                result.update(loaded)
            except Exception as e:
                _logger.error("Error loading credentials from %s: %s", fp, e)
        return result

    def get_credential(
        self, config: "CredentialManager.CredentialConfig"
    ) -> Optional[BaseCredential]:
        """Look up a credential by IRI.

        Uses combined matching: exact, then stored-in-search (most specific),
        then search-in-stored (broadest). Falls back to getpass if fallback='ask'.

        Parameters
        ----------
        config
            Lookup configuration with IRI and fallback strategy.
        """
        file_creds = self._load_file_credentials()
        store_creds = _credentials.get()
        all_creds = {**file_creds, **store_creds}

        cred = find_credential(config.iri, all_creds)
        if cred is not None:
            return cred

        # Fallback
        fallback = config.fallback
        if isinstance(fallback, str):
            fallback = self.CredentialFallback(fallback)

        if fallback == self.CredentialFallback.ask:
            if self.cred_filepath:
                paths = ", ".join(str(fp) for fp in self.cred_filepath)
                print(
                    f"No credentials for {config.iri} found in '{paths}'. "
                    f"Please use the prompt to login"
                )
            username = input("Enter username: ")
            password = getpass.getpass("Enter password: ")
            cred = UserPwdCredential(
                iri=config.iri,
                username=username,
                password=SecretStr(password),
            )
            self.add_credential(cred)
            if self.cred_filepath:
                self.save_credentials_to_file()
            return cred

        return None

    def add_credential(self, cred: BaseCredential):
        """Add a credential to the global store."""
        set_credential(cred)

    def iri_in_credentials(self, iri: str) -> bool:
        """Check if a credential for the given IRI exists in the store."""
        creds = _credentials.get()
        return iri in creds

    def iri_in_file(self, iri: str) -> bool:
        """Check if a credential for the given IRI exists in any YAML file."""
        file_creds = self._load_file_credentials()
        return iri in file_creds

    def save_credentials_to_file(
        self,
        filepath: Optional[Union[str, Path]] = None,
    ):
        """Save in-memory credentials to YAML file(s).

        Parameters
        ----------
        filepath
            Target file. If None, uses the configured cred_filepath(s).
        """
        targets = [Path(filepath)] if filepath else (self.cred_filepath or [])
        creds = _credentials.get()
        for fp in targets:
            fp = Path(fp)
            existing = {}
            if fp.exists():
                try:
                    existing = load_credentials(fp, into_store=False)
                except Exception:
                    pass
            merged = {**existing}
            merged.update(creds)
            dump_credentials(fp, credentials=merged)
            _logger.info("Credentials saved to '%s'.", fp.resolve())
