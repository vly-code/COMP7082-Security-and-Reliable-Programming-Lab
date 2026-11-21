"""Models for the intentionally imperfect order-management application."""
from dataclasses import dataclass
from decimal import Decimal


class CartError(ValueError):
    """Raised when a cart operation receives an invalid quantity."""

@dataclass
class Product:
    sku: str
    name: str
    # FIX: Changed price to use decimal
    price: Decimal
    stock: int


@dataclass
class CartLine:
    sku: str
    name: str
    # FIX: Changed unit_price to use decimal
    unit_price: Decimal
    quantity: int


@dataclass
class OrderResult:
    order_id: int | None
    status: str
    # FIX: Changed total to use decimal
    total: Decimal
