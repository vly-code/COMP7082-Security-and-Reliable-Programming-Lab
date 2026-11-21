"""SQLite persistence."""
import sqlite3
from models import Product
from money import money
import sqlite3


class StoreRepository:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=2)

    def get_product(self, sku):
        conn = self.connect()
        # FIX: parameterised query (removed f-string to prevent SQL injection)
        row = conn.execute('SELECT sku, name, price, stock FROM products WHERE sku = ?',
                           (sku,)).fetchone()
        conn.close()
        return Product(row[0], row[1], money(row[2]), row[3]) if row else None

    def get_saved_cart(self, user_id):
        conn = self.connect()
        # FIX: parameterised query (removed f-string to prevent SQL injection)
        rows = conn.execute('SELECT sku, quantity FROM saved_cart WHERE user_id = ?',
                            (user_id,)).fetchall()
        conn.close()
        return rows

    def save_cart(self, user_id, lines):
        conn = self.connect()
        conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (user_id,))
        for line in lines:
            conn.execute('INSERT INTO saved_cart VALUES (?, ?, ?)', (user_id, line.sku, line.quantity))
        conn.commit()
        conn.close()

    def _adjust_stock(self, lines, sign):
        conn = self.connect()
        try:
            for line in lines:
                conn.execute('UPDATE products SET stock = stock + ? WHERE sku = ?',
                             (sign * line.quantity, line.sku))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reserve_stock(self, lines):
        self._adjust_stock(lines, -1)

    def release_stock(self, lines):
        self._adjust_stock(lines, +1)

    def save_order(self, user_id, amount, status, request_id):
        conn = self.connect()
        cur = conn.execute('INSERT INTO orders(user_id, amount, status, request_id) VALUES (?, ?, ?, ?)',
                           (user_id, float(money(amount)), status, request_id))
        conn.commit()
        order_id = cur.lastrowid
        conn.close()
        return order_id

    def list_orders(self, user_id):
        conn = self.connect()
        # FIX: changed to only show correct user's order not everyone's
        rows = conn.execute('SELECT id, user_id, amount, status FROM orders '
                            'WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()
        conn.close()
        return [(r[0], r[1], money(r[2]) if r[2] is not None else None, r[3]) for r in rows]
