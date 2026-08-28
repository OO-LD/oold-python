"""``format`` assertion.

``format`` is an annotation by default in JSON Schema 2020-12: on its own, a value violating a
declared ``format`` is not an error. This module asserts it instead, so a generated instance that
violates a declared ``format`` is a failure rather than a silent pass.

Most formats are asserted by the checkers ``jsonschema[format-nongpl]`` registers on
``Draft202012Validator.FORMAT_CHECKER`` (see the ``validation`` extra in ``pyproject.toml``). That
extra, not ``jsonschema[format]``, is deliberate: ``jsonschema[format]`` pulls in ``rfc3987``,
which is GPLv3+, into a package that is Apache-2.0. ``format-nongpl`` covers the same formats this
module needs through ``fqdn`` (MPL-2.0), ``rfc3986-validator`` (MIT) and ``rfc3987-syntax``
(Apache-2.0) instead, none of which carry that obligation.

Five formats stay hand-written because the library's own checker disagrees with the reference
toolchain (ajv-formats in *full* mode, which is what ``tests/data/format_parity.json`` records) on
cases this project's schemas rely on:

* ``date-time`` and ``time`` - ``rfc3339_validator`` rejects the space date/time separator, an
  offset without a colon (``+0200``) and the leap second ``23:59:60``, all of which the reference
  toolchain accepts.
* ``email`` and ``idn-email`` - the library's checker for both is not conditional on any optional
  package; it is always just ``"@" in instance``, far looser than ajv-formats' full email pattern.
* ``uuid`` - the library's checker parses with :class:`uuid.UUID`, which strips a leading
  ``urn:uuid:``, and then range-checks dash positions assuming no prefix was there, so a prefixed
  UUID such as ``urn:uuid:...`` is rejected even though the reference toolchain accepts it.

Formats not implemented here stay annotations: an unrecognized ``format`` value is not an error.
"""

from __future__ import annotations

import re
from datetime import date as _date
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

# ---------------------------------------------------------------------------- checker

#: The format checker used everywhere in this package. Kept as a module-level singleton so a
#: validator built in one check behaves identically to one built in another.
OOLD_FORMAT_CHECKER = FormatChecker()

# Formats where jsonschema[format-nongpl]'s own checker matches the reference toolchain on every
# case in tests/data/format_parity.json, plus this project's own edge cases - a compact IRI such
# as `ex:alice` is accepted by `iri`/`iri-reference`/`uri`/`uri-reference` alike, since an IRI is
# a superset of a URI. Copied from the draft this project targets rather than relying on
# jsonschema's ambient global registry, which also carries formats this module does not use
# (e.g. `color`, registered only for draft 3).
for _name in (
    "date",
    "duration",
    "hostname",
    "idn-hostname",
    "ipv4",
    "ipv6",
    "iri",
    "iri-reference",
    "json-pointer",
    "regex",
    "relative-json-pointer",
    "uri",
    "uri-reference",
):
    OOLD_FORMAT_CHECKER.checkers[_name] = Draft202012Validator.FORMAT_CHECKER.checkers[_name]

#: ``format`` values that constrain a string to IRI/URI shape. Used by the pattern lint.
IRI_FORMATS = frozenset({"iri-reference", "iri", "uri-reference", "uri"})


def is_iri_reference(value: str) -> bool:
    """True for an IRI reference: absolute, compact or relative."""
    return isinstance(value, str) and OOLD_FORMAT_CHECKER.conforms(value, "iri-reference")


def is_iri(value: str) -> bool:
    """True for an absolute IRI, meaning an IRI reference that carries a scheme."""
    return isinstance(value, str) and OOLD_FORMAT_CHECKER.conforms(value, "iri")


# ---------------------------------------------------------------------------- hand-written formats

# Ported from ajv-formats so the two toolchains agree on edge cases. ajv matches a loose regex
# and then range-checks the fields numerically, which is what stops `25:00:00` being accepted;
# the same split is used here. `date-time` accepts a space separator and requires an offset,
# `time` leaves the offset optional in its grammar (though not by default here, see
# `_valid_time`), and both allow the leap second 23:59:60.
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d(?:\.\d+)?)(z|[+-]\d\d(?::?\d\d)?)?$", re.IGNORECASE)
_DATE_TIME_SPLIT = re.compile(r"^(.+?)[t ](.+)$", re.IGNORECASE)
# ajv-formats' *full* email pattern, the variant `addFormats(ajv)` installs by default. It
# differs from the fast variant by requiring a dotted domain, so `a@b` is rejected, and by only
# allowing dots between local-part atoms.
_EMAIL = re.compile(
    r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    re.IGNORECASE,
)
_UUID = re.compile(
    r"^(?:urn:uuid:)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _string_check(func):
    """Wrap a predicate so non-strings pass: ``format`` only constrains strings."""

    def check(value: Any) -> bool:
        if not isinstance(value, str):
            return True
        return func(value)

    check.__name__ = func.__name__
    return check


def _register(name: str, predicate) -> None:
    OOLD_FORMAT_CHECKER.checks(name)(_string_check(predicate))


def _valid_date(value: str) -> bool:
    if not _DATE.match(value):
        return False
    try:
        _date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_time(value: str, require_offset: bool = True) -> bool:
    """RFC 3339 full-time, with the field ranges checked numerically as ajv-formats does.

    The offset is *required*, matching ajv-formats' full mode - the variant ``addFormats(ajv)``
    installs by default. Its fast-mode variant makes the offset optional, and following that
    would let ``03:04:05`` pass here.
    """
    match = _TIME.match(value)
    if not match:
        return False
    hour, minute, second = int(match[1]), int(match[2]), float(match[3])
    offset = match[4]
    if require_offset and not offset:
        return False
    if offset and offset.lower() != "z":
        # The offset itself carries an hour and minute that must be in range.
        digits = offset[1:].replace(":", "")
        if int(digits[:2]) > 23 or (len(digits) > 2 and int(digits[2:4]) > 59):
            return False
    if hour <= 23 and minute <= 59 and second < 60:
        return True
    # The leap second is the one legal exception.
    return hour == 23 and minute == 59 and second == 60


def _valid_date_time(value: str) -> bool:
    parts = _DATE_TIME_SPLIT.match(value)
    if not parts:
        return False
    return _valid_date(parts[1]) and _valid_time(parts[2], require_offset=True)


_register("date-time", _valid_date_time)
_register("time", _valid_time)
_register("email", lambda v: bool(_EMAIL.match(v)))
_register("uuid", lambda v: bool(_UUID.match(v)))

# `idn-email` differs from `email` only by permitting non-ASCII, which the IRI rules already do.
# Neither OO-LD corpus uses it; it is registered so a schema that declares it still gets a shape
# check rather than silently no check at all.
_register("idn-email", lambda v: bool(_EMAIL.match(v)) or ("@" in v and is_iri_reference(v)))

#: Deterministic, format-valid sample values, used by the instance generator. Every entry must
#: satisfy the corresponding checker above; :mod:`tests` asserts exactly that.
FORMAT_SAMPLES: dict[str, str] = {
    "date": "2026-01-02",
    "date-time": "2026-01-02T03:04:05Z",
    "time": "03:04:05Z",
    "duration": "P1DT2H",
    "email": "someone@example.org",
    "idn-email": "someone@example.org",
    "hostname": "example.org",
    "idn-hostname": "example.org",
    "ipv4": "192.0.2.1",
    "ipv6": "2001:db8::1",
    "uuid": "00000000-0000-4000-8000-000000000000",
    "regex": "^example$",
    "json-pointer": "/example",
    "relative-json-pointer": "0/example",
    "uri": "https://example.org/thing",
    "uri-reference": "https://example.org/thing",
    "iri": "https://example.org/thing",
    "iri-reference": "https://example.org/thing",
}
