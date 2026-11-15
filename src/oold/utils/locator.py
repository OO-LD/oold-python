"""Finding a published schema in a working tree.

A schema refers to another by the IRI it is published under, because that is what resolves for
a consumer. While it is being edited the same document is a file, and the file is the source of
truth: reading it from disk keeps a build offline and shows the version being worked on rather
than the one already released.

The mapping from IRI to file is the only part of that which is layout-specific, so it is stated
as data. A :class:`MirrorRule` names one IRI prefix and where the segments after it sit under
the root; everything else - following references, reading documents - is the same whatever the
tree looks like. A consumer with a different layout passes different rules, and one with no tree
at all (a browser, a remote store) implements :class:`~oold.utils.mappings.ScopeSource` instead.

With no rule the locator still resolves a relative reference against the referring document,
which is how sibling schemas point at each other.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MirrorRule:
    """One published IRI prefix, and where the document it names sits under the root.

    ``template`` is formatted with the path segments that follow ``prefix``, so
    ``MirrorRule("https://example.org/schemas/", "{0}/{2}", 3)`` reads
    ``https://example.org/schemas/<module>/<version>/<Name>`` as ``<root>/<module>/<Name>``:
    the version is part of the published identity and not of the tree.

    ``segments`` is the number of segments the rule expects, and ``None`` accepts any count. It
    is stated rather than inferred from the template because a template need not mention every
    segment, and a rule that silently matched a shorter IRI would resolve one document to
    another.
    """

    prefix: str
    template: str
    segments: int | None = None

    def path_under(self, root: Path, iri: str) -> Path | None:
        """Where ``iri`` would sit under ``root``, or ``None`` when the rule does not apply."""
        if not iri.startswith(self.prefix):
            return None
        parts = iri[len(self.prefix) :].split("/")
        if self.segments is not None and len(parts) != self.segments:
            return None
        try:
            relative = self.template.format(*parts)
        except (IndexError, KeyError):
            return None
        return root / relative


class Locator:
    """Resolves references to documents in a working tree, and reads them.

    A *key* is this class's name for a located document: an absolute path as a string. Keys are
    compared for identity, which is what lets a caller detect a cycle, so a document reached two
    ways is one key.
    """

    def __init__(
        self,
        root: Path | str | None = None,
        rules: Sequence[MirrorRule] = (),
        encoding: str = "utf-8",
    ) -> None:
        self.root = Path(root) if root is not None else None
        self.rules = tuple(rules)
        self.encoding = encoding
        self._documents: dict[str, dict[str, Any]] = {}

    def locate(self, target: str, origin: str | None = None) -> str | None:
        """The key of the document ``target`` names, or ``None`` when the tree has no such file.

        A fragment is dropped first: it selects a part of a document and says nothing about
        which document that is.
        """
        if not isinstance(target, str) or not target:
            return None
        path = target.partition("#")[0]
        if not path:
            return origin
        if self.root is not None:
            for rule in self.rules:
                candidate = rule.path_under(self.root, path)
                if candidate is not None and candidate.is_file():
                    return str(candidate.resolve())
        if origin is None:
            return None
        candidate = Path(origin).parent / path
        return str(candidate.resolve()) if candidate.is_file() else None

    def read(self, key: str) -> dict[str, Any]:
        """The document at ``key``, parsed once and kept, since a chain revisits a base."""
        if key not in self._documents:
            self._documents[key] = json.loads(Path(key).read_text(encoding=self.encoding))
        return self._documents[key]

    def loader(self, origin: str | None) -> Callable[[str], dict[str, Any] | None]:
        """A ``$ref`` resolver for :func:`oold.utils.mappings.chain`, relative to ``origin``.

        Returns ``None`` for a reference the tree cannot reach, which is what makes a chain
        walk skip that branch instead of failing on half-written input.
        """

        def resolve(ref: str) -> dict[str, Any] | None:
            key = self.locate(ref, origin)
            return self.read(key) if key is not None else None

        return resolve

    def term_chain(self, key: str) -> list[str]:
        """``key`` and every document whose terms it needs, base first.

        A reading needs every term the document can use, and a schema reaches terms three ways:
        it extends a base with ``allOf``, it names another schema in its ``@context``, and it
        points a property at another schema with ``$ref``. Following only ``allOf`` leaves the
        terms of an embedded object undefined, so those keys are dropped on the way to RDF
        without anything saying so.

        This is deliberately wider than :func:`oold.utils.mappings.chain`, which follows
        ``allOf`` alone because inheritance is what decides the *consensus* of a term.
        """
        order: list[str] = []
        # A document is marked before its references are followed, not after, because two
        # schemas may legitimately reference each other and a reference may point back into
        # the document it sits in. Keyed on the resolved document, so the guard holds however
        # the reference was written.
        entered: set[str] = set()

        def references(node: Any) -> list[str]:
            found: list[str] = []
            if isinstance(node, dict):
                target = node.get("$ref")
                if isinstance(target, str):
                    found.append(target)
                for value in node.values():
                    found += references(value)
            elif isinstance(node, list):
                for value in node:
                    found += references(value)
            return found

        def walk(current: str) -> None:
            if current in entered:
                return
            entered.add(current)
            try:
                schema = self.read(current)
            except (OSError, ValueError):
                return
            context = schema.get("@context")
            for entry in context if isinstance(context, list) else [context]:
                if isinstance(entry, str):
                    nested = self.locate(entry, current)
                    if nested is not None:
                        walk(nested)
            for target in references(schema):
                nested = self.locate(target, current)
                if nested is not None:
                    walk(nested)
            order.append(current)

        walk(key)
        return order
