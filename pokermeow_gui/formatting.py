from decimal import Decimal, InvalidOperation


def decimal_or_zero(value):
    try:
        amount = Decimal(str(value))
        if amount.is_finite():
            return amount
    except (InvalidOperation, TypeError, ValueError):
        pass
    return Decimal(0)


def display_amount(value):
    try:
        amount = Decimal(str(value))
        if amount.is_finite():
            return format(amount.normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        pass
    return str(value)
