"""``format`` assertion.

``format`` is an annotation by default in JSON Schema 2020-12: on its own, a value violating a
declared ``format`` is not an error. This module asserts it instead, so a generated instance that
violates a declared ``format`` is a failure rather than a silent pass.

Two reasons it implements the formats itself instead of relying on ``jsonschema[format]``:

* the stock :data:`jsonschema.Draft202012Validator.FORMAT_CHECKER` asserts only eight formats
  without optional packages installed, and the ones OO-LD leans on most (``iri``, ``uri``,
  ``date-time``, ``duration``, ``time``) are not among them;
* ``iri`` and ``iri-reference`` need a deliberate *override* rather than a strict RFC 3987
  implementation. See :func:`is_iri_reference`.

Formats not implemented here stay annotations: an unrecognized ``format`` value is not an error.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date as _date
from typing import Any

from jsonschema import FormatChecker

# ---------------------------------------------------------------------------- IRI

# IRI formats (RFC 3987).
#
# jsonschema's stock Draft202012Validator.FORMAT_CHECKER asserts only eight formats without
# optional packages installed (date, email, idn-email, idn-hostname, ipv4, ipv6, regex, uuid),
# and none of them is iri or iri-reference, so this module implements both against RFC 3987
# itself: an IRI reference excludes ASCII controls, space and the delimiters RFC 3987 disallows,
# while non-ASCII ucschar stays allowed; an absolute IRI additionally begins with a scheme. A
# compact IRI such as `ex:alice` is accepted, since any URI/IRI grammar accepts one - an IRI is a
# superset of a URI.
_IRI_EXCLUDED = re.compile(r"[\s<>\"{}|\\^`]")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

#: ``format`` values that constrain a string to IRI/URI shape. Used by the pattern lint.
IRI_FORMATS = frozenset({"iri-reference", "iri", "uri-reference", "uri"})


def is_iri_reference(value: str) -> bool:
    """True for an IRI reference: absolute, compact or relative."""
    return isinstance(value, str) and not _IRI_EXCLUDED.search(value)


def is_iri(value: str) -> bool:
    """True for an absolute IRI, meaning an IRI reference that carries a scheme."""
    return is_iri_reference(value) and bool(_SCHEME.match(value))


# ---------------------------------------------------------------------------- patterns

# Ported from ajv-formats so the two toolchains agree on edge cases. ajv matches a loose regex
# and then range-checks the fields numerically, which is what stops `25:00:00` being accepted;
# the same split is used here. `date-time` accepts a space separator and requires an offset,
# `time` leaves the offset optional, and both allow the leap second 23:59:60.
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d(?:\.\d+)?)(z|[+-]\d\d(?::?\d\d)?)?$", re.IGNORECASE)
_DATE_TIME_SPLIT = re.compile(r"^(.+?)[t ](.+)$", re.IGNORECASE)
_DURATION = re.compile(r"^P(?!$)((\d+Y)?(\d+M)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?|(\d+W)?)$")
# ajv-formats' *full* email pattern, the variant `addFormats(ajv)` installs by default. It
# differs from the fast variant by requiring a dotted domain, so `a@b` is rejected, and by only
# allowing dots between local-part atoms.
_EMAIL = re.compile(
    r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    re.IGNORECASE,
)
_HOSTNAME = re.compile(
    r"^(?=.{1,253}\.?$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[-0-9a-z]{0,61}[0-9a-z])?)*\.?$",
    re.IGNORECASE,
)
_UUID = re.compile(
    r"^(?:urn:uuid:)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_JSON_POINTER = re.compile(r"^(?:/(?:[^~/]|~0|~1)*)*$")
_RELATIVE_JSON_POINTER = re.compile(r"^(?:0|[1-9][0-9]*)(?:#|(?:/(?:[^~/]|~0|~1)*)*)$")

#: An ASCII-only counterpart of the IRI rule, which is what separates ``uri`` from ``iri``.
_NON_ASCII = re.compile(r"[^\x00-\x7f]")


def _is_uri_reference(value: str) -> bool:
    return is_iri_reference(value) and not _NON_ASCII.search(value)


def _is_uri(value: str) -> bool:
    return _is_uri_reference(value) and bool(_SCHEME.match(value))


# ---------------------------------------------------------------------------- checker

#: The format checker used everywhere in this package. Kept as a module-level singleton so a
#: validator built in one check behaves identically to one built in another.
OOLD_FORMAT_CHECKER = FormatChecker()


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


def _valid_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def _valid_ipv6(value: str) -> bool:
    # A scoped address such as `fe80::1%eth0` is accepted by `ipaddress` but not by ajv, and a
    # zone identifier is not part of the JSON Schema `ipv6` format.
    if "%" in value:
        return False
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return False
    return True


def _valid_regex(value: str) -> bool:
    try:
        re.compile(value)
    except re.error:
        return False
    return True


_register("date", _valid_date)
_register("date-time", _valid_date_time)
_register("time", _valid_time)
_register("duration", lambda v: bool(_DURATION.match(v)))
_register("email", lambda v: bool(_EMAIL.match(v)))
_register("hostname", lambda v: bool(_HOSTNAME.match(v)))
_register("ipv4", _valid_ipv4)
_register("ipv6", _valid_ipv6)
_register("uuid", lambda v: bool(_UUID.match(v)))
_register("regex", _valid_regex)
_register("json-pointer", lambda v: bool(_JSON_POINTER.match(v)))
_register("relative-json-pointer", lambda v: bool(_RELATIVE_JSON_POINTER.match(v)))
_register("uri", _is_uri)
_register("uri-reference", _is_uri_reference)
_register("iri", is_iri)
_register("iri-reference", is_iri_reference)

# The internationalised variants differ from their ASCII counterparts only by permitting
# non-ASCII, which the IRI rules already do. Neither OO-LD corpus uses them; they are registered
# so a schema that declares one still gets a shape check rather than silently no check at all.
_register("idn-email", lambda v: bool(_EMAIL.match(v)) or ("@" in v and is_iri_reference(v)))
_register("idn-hostname", lambda v: is_iri_reference(v) and "/" not in v)

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
