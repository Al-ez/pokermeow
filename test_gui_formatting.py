from decimal import Decimal

from pokermeow_gui.formatting import decimal_or_zero, display_amount


def test_display_amount_preserves_existing_number_formatting():
    assert display_amount(Decimal("750.50")) == "750.5"
    assert display_amount("0E+3") == "0"
    assert display_amount("not a number") == "not a number"


def test_decimal_or_zero_rejects_invalid_and_non_finite_values():
    assert decimal_or_zero("12.50") == Decimal("12.50")
    assert decimal_or_zero("NaN") == Decimal(0)
    assert decimal_or_zero(None) == Decimal(0)
