"""Unit tests that need no disc image.

`verify.py` is the other half of the testing story and it is the more important
half: it measures the library against a real disc. These tests measure the parts
that can be exercised on fabricated input, which is the only way to reach a form
the shipped game does not happen to contain.

Run: python -m unittest discover -s tests -t .
"""
