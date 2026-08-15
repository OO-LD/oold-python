"""Experimental, non-shipping prototypes.

Modules here validate design directions (see
``docs/design/graph-object-binding.md``) without touching the shipped
``oold.model``. They are intentionally isolated: importing this package must
not trigger the process-wide ``pydantic.fields.FieldInfo`` monkeypatch that
``oold.model`` performs.
"""
