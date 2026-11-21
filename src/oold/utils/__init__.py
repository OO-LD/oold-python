"""Operations on OO-LD documents and the contexts that give them meaning.

Each module here stands on its own and is imported by path, so nothing is re-exported from
this file: a consumer takes ``oold.utils.mappings`` and pays for nothing else.

The package carried no ``__init__.py`` until these modules arrived. It imported anyway, as an
implicit namespace package, but static tooling could not see it as a member of ``oold``, so the
documentation build could not collect any module in it.
"""
