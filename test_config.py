import pytest

import config


def test_environment_int_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("POKERMEOW_TEST_VALUE", raising=False)
    assert config._environment_int("POKERMEOW_TEST_VALUE", 7) == 7


def test_environment_int_reads_valid_value(monkeypatch):
    monkeypatch.setenv("POKERMEOW_TEST_VALUE", "12")
    assert config._environment_int("POKERMEOW_TEST_VALUE", 7) == 12


@pytest.mark.parametrize("value", ["nope", "1.5", ""])
def test_environment_int_rejects_non_integer(monkeypatch, value):
    monkeypatch.setenv("POKERMEOW_TEST_VALUE", value)
    with pytest.raises(RuntimeError, match="must be a whole number"):
        config._environment_int("POKERMEOW_TEST_VALUE", 7)


def test_environment_int_enforces_minimum(monkeypatch):
    monkeypatch.setenv("POKERMEOW_TEST_VALUE", "0")
    with pytest.raises(RuntimeError, match="must be at least 1"):
        config._environment_int("POKERMEOW_TEST_VALUE", 7)
