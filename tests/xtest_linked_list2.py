# from typing import List as _List

# class CustomList(_List):
#     """A custom list that extends the built-in list."""
#     def custom_method(self):
#         return "This is a custom method"

# # Patch the typing module
# import typing
# setattr(typing, "List", CustomList)
# from typing import List as __List
# l = __List([1, 2, 3])
# l.cu
# print(__List)

from typing import (
    List,  # works, but static type checkers will not recognize it as LinkedBaseModelList
)

# from test_linked_list import LinkedBaseModelList as List # works
# from typing import List # does not work, not yet patched
from test_linked_list import TestLinkedBaseModel


class MyClass(TestLinkedBaseModel):
    my_list: List[int]


m = MyClass(my_list=[])
print(m.my_list._synced_iri_list)
