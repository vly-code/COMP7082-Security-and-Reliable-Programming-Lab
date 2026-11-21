import os, tempfile, unittest
from decimal import Decimal as D

from cart import ShoppingCart
from checkout import CheckoutService
from models import CartError
from payments import FakePaymentGateway
from repository import StoreRepository
from setup_db import initialize

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 't.db')
        initialize(self.path)
        self.repo = StoreRepository(self.path)
        self.gw = FakePaymentGateway()
        self.svc = CheckoutService(self.repo, self.gw)

    def tearDown(self):
        self.tmp.cleanup()

    def cart(self, user='u1', **items):
        c = ShoppingCart(user, self.repo)
        for sku, q in items.items():
            self.assertTrue(c.add_item(sku.replace('_', '-'), q))
        return c

    def stock(self, sku):
        return self.repo.get_product(sku).stock


class MoneyTests(Base):                                   # defect 1: floats -> Decimal
    def test_product_and_line_prices_are_decimal(self):
        p = self.repo.get_product('MOU-01')
        self.assertIsInstance(p.price, D); self.assertEqual(p.price, D('29.95'))
        self.assertIsInstance(self.cart(MOU_01=1).lines[0].unit_price, D)

    def test_arithmetic_has_no_float_drift(self):
        self.assertNotEqual(999.99 * 3, 2999.97)          # float drift: 2999.9700000000003
        self.assertEqual(self.cart(LAP_01=3).subtotal(), D('2999.97'))
        self.assertNotEqual(29.95 * 3 + 9.99, 99.84)      # float drift: 99.83999999999999
        self.assertEqual(self.cart(MOU_01=3, USB_01=1).subtotal(), D('99.84'))

    def test_order_total_is_decimal_and_round_trips_through_db(self):
        c = self.cart(MOU_01=3); c.apply_discount('WELCOME10')        # 89.85 - 8.99 (8.985 half-up)
        r = self.svc.checkout(c, 'tok', 'r1')
        self.assertIsInstance(r.total, D); self.assertEqual(r.total, D('80.86'))
        (_, _, amount, _), = self.repo.list_orders('u1')
        self.assertIsInstance(amount, D); self.assertEqual(amount, D('80.86'))
        self.assertEqual(self.gw.calls, [(D('80.86'), 'tok')])


class QuantityTests(Base):                                # defects 2, 3
    def test_invalid_quantities_raise(self):
        c = self.cart(MOU_01=2)
        for q in (0, -3, 1.5, True, '2'):
            with self.assertRaises(CartError): c.add_item('MOU-01', q)
            with self.assertRaises(CartError): c.remove_item('MOU-01', q)
        self.assertEqual(c.lines[0].quantity, 2)

    def test_stock_check_counts_existing_cart_quantity(self):
        c = self.cart(LAP_01=3)                           # laptop stock is 5
        self.assertFalse(c.add_item('LAP-01', 3))         # 3 + 3 > 5
        self.assertEqual(c.lines[0].quantity, 3)
        self.assertTrue(c.add_item('LAP-01', 2))          # 3 + 2 == 5
        self.assertEqual(c.lines[0].quantity, 5)


class DiscountTests(Base):                                # defects 4, 5
    def test_same_coupon_cannot_be_applied_twice(self):
        c = self.cart(MOU_01=2)                           # 59.90
        self.assertTrue(c.apply_discount('WELCOME10'))
        self.assertFalse(c.apply_discount('WELCOME10'))
        self.assertEqual(c.total(), D('53.91'))

    def test_new_coupon_replaces_old_one(self):
        c = self.cart(MOU_01=2)
        c.apply_discount('WELCOME10'); c.apply_discount('STUDENT20')
        self.assertEqual(c.total(), D('47.92'))           # 20% off 59.90, not 20% off 53.91

    def test_total_never_negative(self):
        c = self.cart(USB_01=1)                           # 9.99 < 15.00
        c.apply_discount('SAVE15')
        self.assertEqual(c.total(), D('0.00'))
        self.assertEqual(self.cart(LAP_01=1).total(), D('999.99'))

    def test_save15_on_large_cart_still_works(self):
        c = self.cart(LAP_01=1); c.apply_discount('SAVE15')
        self.assertEqual(c.total(), D('984.99'))

    def test_invalid_coupon(self):
        c = self.cart(MOU_01=1)
        self.assertFalse(c.apply_discount('BOGUS')); self.assertEqual(c.total(), D('29.95'))


class StockReservationTests(Base):                        # defect 6
    def test_paid_keeps_stock_reduced(self):
        r = self.svc.checkout(self.cart(MOU_01=2), 'tok', 'r1')
        self.assertEqual(r.status, 'paid'); self.assertEqual(self.stock('MOU-01'), 18)

    def test_declined_restores_stock(self):
        self.gw.should_approve = False
        r = self.svc.checkout(self.cart(LAP_01=2, USB_01=5), 'tok', 'r1')
        self.assertEqual(r.status, 'declined')
        self.assertEqual((self.stock('LAP-01'), self.stock('USB-01')), (5, 50))

    def test_gateway_error_restores_stock(self):
        class Boom:
            def charge(self, *a): raise TimeoutError('network')
        r = CheckoutService(self.repo, Boom()).checkout(self.cart(LAP_01=2), 'tok', 'r1')
        self.assertEqual(r.status, 'payment_error'); self.assertEqual(self.stock('LAP-01'), 5)

    def test_declined_order_is_still_recorded(self):
        self.gw.should_approve = False
        self.svc.checkout(self.cart(USB_01=1), 'tok', 'r1')
        self.assertEqual([o[3] for o in self.repo.list_orders('u1')], ['declined'])


class RepositoryTests(Base):                              # defects 7, 8
    def test_list_orders_only_returns_own_orders(self):
        self.svc.checkout(self.cart('a', MOU_01=1), 'tok', 'ra')
        self.svc.checkout(self.cart('b', USB_01=1), 'tok', 'rb')
        self.assertEqual([o[1] for o in self.repo.list_orders('a')], ['a'])
        self.assertEqual([o[1] for o in self.repo.list_orders('b')], ['b'])
        self.assertEqual(self.repo.list_orders('nobody'), [])

    def test_sql_injection_is_inert(self):
        self.assertIsNone(self.repo.get_product("x' OR '1'='1"))
        self.assertIsNone(self.repo.get_product("MOU-01' --x"))
        self.assertEqual(self.repo.get_saved_cart("' OR '1'='1"), [])
        c = self.cart('victim', MOU_01=1); c.save()
        self.assertEqual(self.repo.get_saved_cart("' OR '1'='1"), [])
        self.assertEqual(self.repo.get_saved_cart('victim'), [('MOU-01', 1)])
