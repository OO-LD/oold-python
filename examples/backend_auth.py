from oold.backend.auth import SetCredentialParam, UserPwdCredential, set_credential
from oold.backend.sparql import SparqlResolver

# ToDo: allow other ways, e.g. environment variables, keyring, ...
set_credential(
    SetCredentialParam(
        credential=UserPwdCredential(
            iri="https://blazegraph.kiprobatt.de",
            username="user",
            password="*********",
        )
    )
)

r = SparqlResolver(
    endpoint="https://blazegraph.kiprobatt.de/blazegraph/namespace/kb/sparql"
)

# this will lookup the credential and use it for authentication
# raise an error if the credential is missing or invalid
r.resolve_iris(["http://example.com/Entity1"])
