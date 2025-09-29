"""Utilities for working different enviroments like IPython/Jupyter notebooks."""

import ast
import inspect
import sys
from typing import Callable


def is_running_in_ipython() -> bool:
    """Check if the code is running in an interactive
    environment like Jupyter or IPython."""
    return "IPython" in sys.modules


def is_running_in_notebook() -> bool:
    """Check if the code is running in a Jupyter notebook."""
    return "ipykernel" in sys.modules


def is_running_in_pyodide() -> bool:
    """Check if the code is running in a Pyodide environment."""
    return sys.platform == "emscripten"


def get_ipython_source() -> str:
    """Get the source code of the running notebook."""
    from IPython import get_ipython

    shell = get_ipython()
    if shell is None:
        raise RuntimeError("Not running in an IPython environment")

    if not hasattr(shell, "user_ns"):
        raise AttributeError("Cannot access user namespace")

    # list of input cells in the notebook
    input_list = shell.user_ns["In"]

    source_text = "\n\n".join(cell for cell in input_list[1:] if cell)

    return source_text


def get_object_source_from_ipython_source(obj: Callable) -> str:
    """Get the most recent definition of an object in a ipython session."""
    notebook_source = get_ipython_source()
    tree = ast.parse(notebook_source)

    obj_name = obj.__name__

    # Walk the entire tree and get the last matching definition
    segment = None
    for node in ast.walk(tree):
        # Check for function or class definitions, depending on the type of obj
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == obj_name
        ):
            segment = ast.get_source_segment(notebook_source, node)
        elif isinstance(node, ast.ClassDef) and node.name == obj_name:
            segment = ast.get_source_segment(notebook_source, node)

    if segment is not None:
        return segment

    raise ValueError(
        f"Object '{obj_name}' definition not found in the ipython session source code"
    )


def get_object_source(obj: Callable) -> str:
    """Get the source code of an object, works in scripts and ipython sessions."""
    try:
        source = inspect.getsource(obj)
    except OSError:
        # no source code file available
        try:
            if is_running_in_ipython():
                source = get_object_source_from_ipython_source(obj)
            else:
                return None
        except ValueError:
            # no class source available
            return None
    return source
