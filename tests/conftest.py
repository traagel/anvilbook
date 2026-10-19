import pytest


@pytest.fixture(autouse=True)
def classic_recipes(monkeypatch):
    """The tests bring their own recipes, which the shipped Forever table would replace.
    test_forever.py reads the table with forever.read instead."""
    monkeypatch.setattr('anvilbook.forever.load', lambda: None)
