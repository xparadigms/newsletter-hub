"""Code shared by the four newsletter generators.

The generators run with their own directory as the working directory, so the
repository root is not on sys.path. Each main.py puts it there with:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

Two lines, identical in CI and locally, and no workflow or packaging change.
PYTHONPATH would not work because .env is loaded after the interpreter has
already built sys.path.
"""
