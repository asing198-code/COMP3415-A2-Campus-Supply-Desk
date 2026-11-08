"""Shared fixtures for the Campus Supply Desk tests."""

import json
from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class TempStateTestCase(unittest.TestCase):
    """Each test gets its own temporary save file that is never created up front."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"
        self.service = OrderService(self.path)

    def item(self, product_id, quantity):
        return {"product_id": product_id, "quantity": quantity}

    def stock(self, product_id):
        for product in self.service.catalog():
            if product["product_id"] == product_id:
                return product["stock"]
        raise AssertionError("missing product " + product_id)

    def write_state(self, catalog, orders=(), next_order_number=1):
        """Create a save file with a custom catalog (for boundaries the real catalog can't reach)."""
        self.path.write_text(json.dumps({
            "schema_version": 1,
            "next_order_number": next_order_number,
            "catalog": catalog,
            "orders": list(orders),
        }), encoding="utf-8")

    def saved_bytes(self):
        return self.path.read_bytes() if self.path.exists() else None
