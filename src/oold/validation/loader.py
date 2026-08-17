"""A JSON-LD document loader backed by the schema resolver.

This loader maps ``https://oo-ld.test/examples/<file>`` onto the directory under test, which is
what makes relative ``@context`` entries resolve on disk. It additionally serves ``http(s)`` and
``file:`` references through :class:`~oold.validation.resolve.Resolver`, so they are cached
rather than refetched. Passing ``offline=True`` on the resolver restricts resolution to local
files and the warm cache, with the network refused, which also means a schema whose ``@context``
chain leaves the directory cannot be processed at all.

The loader is passed per call via pyld's ``documentLoader`` option rather than installed with
``jsonld.set_document_loader``, so validating two directories in one process (or two MCP tool
calls in one session) cannot leak one run's mapping into another.

An OO-LD schema doubles as a remote context: JSON-LD 1.1 remote-context retrieval uses the
``@context`` member of the fetched document, which is exactly what makes ``"@context":
"Thing.schema.json"`` work.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from pyld import jsonld

from .resolve import Resolver, SchemaResolutionError

#: Synthetic host standing in for the filesystem, using ``https://oo-ld.test/examples/`` as its
#: base. Mounting the *parent* of the directory under test at the host root matches that base
#: exactly whenever the directory is called ``examples``, while also giving ``../`` references
#: somewhere to land.
DEFAULT_HOST = "https://oo-ld.test/"

#: Used when no directory is under test, so ``url_for`` still returns something well-formed.
DEFAULT_BASE = DEFAULT_HOST + "examples/"


class DocumentLoader:
    """Resolves JSON-LD document URLs for one validation run.

    The synthetic host is mounted on the filesystem: its root is the parent of the directory
    under test, and the directory itself sits one segment down. That mapping is what lets a
    ``@context`` reference climb out of the directory - ``"../Thing.schema.json"`` resolves to
    ``https://oo-ld.test/Thing.schema.json`` and lands on the sibling file - which the reference
    harness cannot do, since it only maps names directly under its base.

    Resolved paths are confined to the mounted root, so a crafted ``../../`` reference cannot
    read arbitrary files.
    """

    def __init__(
        self,
        resolver: Resolver,
        directory: Path | None = None,
        host: str = DEFAULT_HOST,
        root: Path | None = None,
    ) -> None:
        self.resolver = resolver
        self.directory = Path(directory).resolve() if directory else None
        self.host = host if host.endswith("/") else host + "/"
        if self.directory is not None:
            self.root = Path(root).resolve() if root else self.directory.parent
            self.base_url = f"{self.host}{self.directory.name}/"
        else:
            self.root = None
            self.base_url = DEFAULT_BASE
        #: URLs this loader was asked for, in order. Useful in tests and ``--verbose``.
        self.requested: list[str] = []

    # pyld calls the loader as loader(url, options).
    def __call__(self, url: str, options: Any = None) -> dict[str, Any]:
        self.requested.append(url)
        document = self._load(url)
        # Hand pyld a private copy. It rewrites a retrieved context's relative references to
        # absolute *in place*, so returning the resolver's cached object would rewrite
        # `"Thing.schema.json"` to `"https://oo-ld.test/examples/Thing.schema.json"` inside the
        # cache. Every later consumer of that document - context resolution, the pattern lint -
        # would then see a synthetic URL it cannot resolve, and the failure would surface far
        # from its cause and only when checks run in a particular order.
        return {"contextUrl": None, "documentUrl": url, "document": deepcopy(document)}

    def _load(self, url: str) -> Any:
        if self.root is not None and url.startswith(self.host):
            target = self._map_to_disk(url)
            try:
                return self.resolver.fetch(target.as_uri())
            except SchemaResolutionError as exc:
                raise _loader_error(str(exc), url) from exc

        try:
            return self.resolver.fetch(url)
        except SchemaResolutionError as exc:
            raise _loader_error(str(exc), url) from exc

    def _map_to_disk(self, url: str) -> Path:
        relative = unquote(urlsplit(url).path).lstrip("/")
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise _loader_error(f"refusing to read {relative!r}: it escapes {self.root}", url) from exc
        if not target.is_file():
            raise _loader_error(f"no such document under {self.root}: {relative}", url)
        return target

    def url_for(self, filename: str) -> str:
        """The synthetic URL a file in the directory under test is addressed by."""
        return f"{self.base_url}{filename}"

    def options(self, **extra: Any) -> dict[str, Any]:
        """pyld options carrying this loader, plus whatever the caller adds."""
        return {"documentLoader": self, **extra}


def _loader_error(message: str, url: str) -> jsonld.JsonLdError:
    """Raise in the shape pyld expects, so failures surface as JSON-LD errors."""
    return jsonld.JsonLdError(
        message,
        "jsonld.LoadDocumentError",
        {"url": url},
        code="loading document failed",
    )


def _message_of(exc: BaseException) -> str:
    """The first line of an exception's message.

    ``JsonLdError.__str__`` renders ``str(self.args)``, so a plain ``str()`` yields a tuple
    repr with a stray parenthesis, plus several trailing metadata lines. Reading ``args[0]``
    directly avoids both.
    """
    args = getattr(exc, "args", ())
    text = args[0] if args and isinstance(args[0], str) else str(exc)
    return text.strip().splitlines()[0]


def describe_jsonld_error(exc: BaseException) -> str:
    """Render a pyld error usefully, surfacing the root cause rather than the wrapper.

    pyld replaces a loader failure with a generic "Dereferencing a URL did not result in a
    valid JSON-LD object" and lists four possible causes, none of which is the actual one. The
    real reason - an offline refusal, a missing file - survives only on the exception chain, so
    that is what gets reported. Without this, an offline run's most common failure reads as an
    unexplained JSON-LD error.
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    root = chain[-1]
    message = _message_of(root)
    if root is not exc:
        code = getattr(exc, "code", None) or getattr(exc, "type", None)
        return f"{message} [{code}]" if code else message
    return message if isinstance(exc, jsonld.JsonLdError) else f"{type(exc).__name__}: {message}"
