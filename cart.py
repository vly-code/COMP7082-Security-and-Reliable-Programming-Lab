"""Business logic."""
from decimal import Decimal
from models import CartError, CartLine
from money import ZERO, money, percent_of


def _check_quantity(quantity):
    # FIX: reject zero, negatives, floats, strings and bools (True == 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise CartError(f'Quantity must be a positive whole number, got {quantity!r}')


class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None
        self.discounted_total = None

    def add_item(self, sku, quantity):
        _check_quantity(quantity)
        product = self.repository.get_product(sku)
        if not product:
            print('Unknown product')
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        # FIX: stock check includes what is already in the cart
        wanted = quantity + (existing.quantity if existing else 0)
        if product.stock < wanted:
            print('Not enough stock')
            return False
        if existing:
            existing.quantity += quantity
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        if quantity is not None:
            _check_quantity(quantity)
        for line in self.lines:
            if line.sku == sku:
                if quantity is None or quantity >= line.quantity:
                    self.lines.remove(line)
                else:
                    line.quantity -= quantity
                return True
        print('Item not found')
        return False

    def subtotal(self):
        return money(sum((line.unit_price * line.quantity for line in self.lines), ZERO))

    def total(self):
        if self.discounted_total is not None:
            return self.discounted_total
        return self.subtotal()

    def apply_discount(self, code):
        # FIX: a coupon can only be applied once; a different code REPLACES the old one
        if code is not None and code == self.discount_code:
            print('Coupon already applied')
            return False
        amount = self.subtotal()
        if code == 'WELCOME10':
            amount -= percent_of(amount, Decimal('10'))
        elif code == 'STUDENT20':
            amount -= percent_of(amount, Decimal('20'))
        elif code == 'SAVE15':
            amount -= Decimal('15.00')
        elif code == 'FREESHIP':
            print('Shipping is free')
        else:
            print('Invalid coupon')
            return False
        self.discount_code = code
        self.discounted_total = max(amount, ZERO)
        return True

    def load(self):
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            self.add_item(sku, quantity)

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
