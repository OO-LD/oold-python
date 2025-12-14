import getpass
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, SecretStr

global _credentials
_credentials = {}


class BaseCredential(BaseModel):
    """Abstract base class for credentials"""

    iri: Union[str, List[str]]
    """the IRI(s) the credential is valid for"""


class UserPwdCredential(BaseCredential):
    """a username - password credential"""

    username: str
    """the user identifier"""
    password: SecretStr
    """the users password"""


class CredentialFallback(str, Enum):
    """Modes of handling missing credentials

    Attributes
    ----------
    none:
        throw error
    ask:
        use getpass to ask for credentials
    """

    ask = "ask"  # use getpass to ask for credentials
    none = "none"  # throw error


class GetCredentialParam(BaseModel):
    """Reads credentials from a yaml file"""

    iri: str
    """internationalized resource identifier / address of the service, may contain
    protocol, domain, port and path matches by "contains" returning the shortest
    match"""
    fallback: Optional[CredentialFallback] = CredentialFallback.none
    """The fallback strategy if no credential was found for the given origin"""


class SetCredentialParam(BaseModel):
    credential: BaseCredential


def set_credential(param: SetCredentialParam) -> None:
    global _credentials
    iris = (
        param.credential.iri
        if isinstance(param.credential.iri, list)
        else [param.credential.iri]
    )
    for iri in iris:
        _credentials[iri] = param.credential


def get_credential(param: GetCredentialParam) -> BaseCredential:
    match_iri = ""
    cred = None
    iris = _credentials.keys()
    for iri in iris:
        if iri in param.iri:
            if match_iri == "" or len(match_iri) > len(
                iri
            ):  # use the less specific match
                match_iri = iri

    if match_iri != "":
        cred = _credentials.get(match_iri, None)

    if cred is None:
        if param.fallback is CredentialFallback.ask:
            print(
                f"No credentials for {param.iri} found. "
                f"Please use the prompt to login"
            )
            username = input("Enter username: ")
            password = getpass.getpass("Enter password: ")
            cred = UserPwdCredential(
                username=username, password=password, iri=param.iri
            )
            set_credential(SetCredentialParam(credential=cred))
    return cred
