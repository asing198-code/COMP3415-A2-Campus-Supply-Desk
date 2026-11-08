"""Service-level tests grouped by the four Task 2 categories."""

import unittest

from supplydesk.service import OrderService
from tests.helpers import TempStateTestCase


class NormalBehaviourTests(TempStateTestCase):
    def test_quote_lines_and_totals_for_spec_examples(self):
        cases = [
            ("regular", [self.item("notebook", 2)], "pickup", (1000, 0, 0, 1000)),
            ("student", [self.item("hoodie", 2)], "delivery", (8000, 800, 600, 7800)),
            ("regular", [self.item("hoodie", 3)], "delivery", (12000, 0, 0, 12000)),
        ]
        for customer, items, fulfillment, expected in cases:
            with self.subTest(customer=customer, fulfillment=fulfillment):
                quote = self.service.quote(customer, items, fulfillment)
                self.assertEqual(
                    (quote["subtotal_cents"], quote["discount_cents"],
                     quote["delivery_cents"], quote["total_cents"]),
                    expected,
                )

    def test_quote_line_contains_product_details(self):
        quote = self.service.quote("regular", [self.item("pen-pack", 3)])
        self.assertEqual(quote["customer_type"], "regular")
        self.assertEqual(quote["fulfillment"], "pickup")
        self.assertEqual(quote["items"], [{
            "product_id": "pen-pack",
            "name": "Pen pack",
            "unit_price_cents": 750,
            "quantity": 3,
            "line_total_cents": 2250,
        }])

    def test_placement_deducts_stock_and_numbers_orders(self):
        first = self.service.place_order("regular", [self.item("mug", 2), self.item("bag", 1)])
        second = self.service.place_order("student", [self.item("mug", 1)], "delivery")
        self.assertEqual((first["order_id"], second["order_id"]), ("ORD-0001", "ORD-0002"))
        self.assertEqual(first["status"], "placed")
        self.assertEqual(self.stock("mug"), 5)
        self.assertEqual(self.stock("bag"), 3)

    def test_list_orders_keeps_placement_order_including_cancelled(self):
        first = self.service.place_order("regular", [self.item("notebook", 1)])
        second = self.service.place_order("regular", [self.item("pen-pack", 1)])
        self.service.cancel_order(first["order_id"])
        orders = self.service.list_orders()
        self.assertEqual([o["order_id"] for o in orders], ["ORD-0001", "ORD-0002"])
        self.assertEqual([o["status"] for o in orders], ["cancelled", "placed"])
        self.assertEqual(orders[1], second)


class BoundaryBehaviourTests(TempStateTestCase):
    def test_student_discount_threshold_is_at_least_5000_cents(self):
        # 9, 10 and 11 notebooks = 4,500 / 5,000 / 5,500 cents.
        expected_discounts = {9: 0, 10: 500, 11: 550}
        for quantity, discount in expected_discounts.items():
            with self.subTest(subtotal=quantity * 500):
                quote = self.service.quote("student", [self.item("notebook", quantity)])
                self.assertEqual(quote["discount_cents"], discount)
                self.assertEqual(quote["total_cents"], quantity * 500 - discount)

    def test_regular_customer_never_gets_discount(self):
        quote = self.service.quote("regular", [self.item("hoodie", 5)])
        self.assertEqual(quote["discount_cents"], 0)

    def test_free_delivery_threshold_is_at_least_10000_after_discount(self):
        below = self.service.quote("regular", [self.item("notebook", 19)], "delivery")  # 9,500
        at = self.service.quote("regular", [self.item("notebook", 20)], "delivery")  # 10,000
        self.assertEqual(below["delivery_cents"], 600)
        self.assertEqual(at["delivery_cents"], 0)
        # Student: subtotal 10,500 is over the threshold, but 10,500 - 1,050 = 9,450 is not.
        student = self.service.quote(
            "student", [self.item("hoodie", 2), self.item("bag", 1)], "delivery")
        self.assertEqual(student["discount_cents"], 1050)
        self.assertEqual(student["delivery_cents"], 600)
        self.assertEqual(student["total_cents"], 10050)

    def test_discount_rounds_half_cent_upward(self):
        self.write_state([{"product_id": "kit", "name": "Kit",
                           "unit_price_cents": 5005, "stock": 3}])
        quote = self.service.quote("student", [self.item("kit", 1)])
        self.assertEqual(quote["discount_cents"], 501)  # 500.5 rounds up
        self.assertEqual(quote["total_cents"], 4504)

    def test_quantity_limits_1_and_99_accepted_0_and_100_rejected(self):
        self.write_state([{"product_id": "clip", "name": "Clip",
                           "unit_price_cents": 10, "stock": 500}])
        for quantity in (1, 99):
            with self.subTest(quantity=quantity):
                self.assertEqual(
                    self.service.quote("regular", [self.item("clip", quantity)])["subtotal_cents"],
                    quantity * 10)
        for quantity in (0, -1, 100):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    self.service.quote("regular", [self.item("clip", quantity)])

    def test_ordering_all_remaining_stock_then_one_more(self):
        self.service.place_order("regular", [self.item("bag", 4)])
        self.assertEqual(self.stock("bag"), 0)
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [self.item("bag", 1)])

    def test_duplicate_lines_within_stock_stay_separate(self):
        quote = self.service.quote("regular", [self.item("bag", 2), self.item("bag", 2)])
        self.assertEqual(len(quote["items"]), 2)
        self.assertEqual(quote["subtotal_cents"], 10000)


class InvalidBehaviourTests(TempStateTestCase):
    def assert_rejected_everywhere(self, customer, items, fulfillment="pickup"):
        """Both operations must raise ValueError and leave saved data untouched."""
        before = self.saved_bytes()
        with self.assertRaises(ValueError):
            self.service.quote(customer, items, fulfillment)
        with self.assertRaises(ValueError):
            self.service.place_order(customer, items, fulfillment)
        self.assertEqual(self.saved_bytes(), before)

    def test_invalid_customer_and_fulfillment(self):
        for customer, fulfillment in (("Student", "pickup"), ("staff", "pickup"),
                                      ("", "pickup"), ("regular", "courier"),
                                      ("regular", "Delivery"), ("regular", None)):
            with self.subTest(customer=customer, fulfillment=fulfillment):
                self.assert_rejected_everywhere(customer, [self.item("notebook", 1)], fulfillment)

    def test_invalid_item_lists(self):
        for items in ([], None, "notebook:1", ["notebook"], [{"product_id": "notebook"}],
                      [{"quantity": 1}], [self.item("laptop", 1)]):
            with self.subTest(items=items):
                self.assert_rejected_everywhere("regular", items)

    def test_quantities_must_be_real_integers(self):
        for quantity in (True, 2.0, 1.5, "2", None):
            with self.subTest(quantity=quantity):
                self.assert_rejected_everywhere("regular", [self.item("notebook", quantity)])

    def test_quantity_above_stock(self):
        self.assert_rejected_everywhere("regular", [self.item("hoodie", 6)])

    def test_duplicate_lines_combined_over_stock_are_rejected(self):
        # Notebook stock is 20; 15 + 10 = 25 must be rejected even though each line fits.
        self.assert_rejected_everywhere(
            "regular", [self.item("notebook", 15), self.item("notebook", 10)])
        self.assertEqual(self.stock("notebook"), 20)

    def test_rejected_request_after_saved_order_changes_nothing(self):
        self.service.place_order("regular", [self.item("mug", 1)])
        self.assert_rejected_everywhere("regular", [self.item("mug", 1), self.item("laptop", 1)])
        self.assertEqual(self.stock("mug"), 7)
        nxt = self.service.place_order("regular", [self.item("mug", 1)])
        self.assertEqual(nxt["order_id"], "ORD-0002")

    def test_unknown_order_id(self):
        self.service.place_order("regular", [self.item("mug", 1)])
        before = self.saved_bytes()
        for action in (self.service.get_order, self.service.cancel_order):
            with self.subTest(action=action.__name__):
                with self.assertRaises(ValueError):
                    action("ORD-9999")
        self.assertEqual(self.saved_bytes(), before)

    def test_malformed_save_file_raises_instead_of_resetting(self):
        self.path.write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [self.item("mug", 1)])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{not valid json")


class PreservedBehaviourTests(TempStateTestCase):
    def test_quote_matches_subsequent_order(self):
        items = [self.item("hoodie", 1), self.item("mug", 2), self.item("hoodie", 1)]
        for customer, fulfillment in (("regular", "pickup"), ("student", "delivery")):
            with self.subTest(customer=customer, fulfillment=fulfillment):
                quote = self.service.quote(customer, items, fulfillment)
                order = self.service.place_order(customer, items, fulfillment)
                self.assertEqual({k: v for k, v in order.items()
                                  if k not in ("order_id", "status")}, quote)

    def test_defaults_are_pickup(self):
        self.assertEqual(self.service.quote("regular", [self.item("mug", 1)])["fulfillment"],
                         "pickup")
        self.assertEqual(self.service.place_order("regular", [self.item("mug", 1)])["fulfillment"],
                         "pickup")

    def test_catalog_and_quote_do_not_create_save_file(self):
        self.service.catalog()
        self.service.quote("student", [self.item("hoodie", 2)], "delivery")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.stock("hoodie"), 5)

    def test_reopening_preserves_orders_stock_and_numbering(self):
        order = self.service.place_order("student", [self.item("hoodie", 2)], "delivery")
        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order("ORD-0001"), order)
        self.assertEqual(reopened.list_orders(), [order])
        self.assertEqual(reopened.catalog(), self.service.catalog())
        self.assertEqual(reopened.place_order("regular", [self.item("mug", 1)])["order_id"],
                         "ORD-0002")

    def test_cancel_keeps_original_details_and_restores_stock(self):
        order = self.service.place_order("student", [self.item("hoodie", 2)], "delivery")
        cancelled = self.service.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual({k: v for k, v in cancelled.items() if k != "status"},
                         {k: v for k, v in order.items() if k != "status"})
        self.assertEqual(self.stock("hoodie"), 5)
        self.assertEqual(OrderService(self.path).get_order("ORD-0001")["status"], "cancelled")

    def test_cancelling_twice_does_not_restore_stock_again(self):
        order = self.service.place_order("regular", [self.item("bag", 2)])
        first = self.service.cancel_order(order["order_id"])
        second = self.service.cancel_order(order["order_id"])
        self.assertEqual(second, first)
        self.assertEqual(self.stock("bag"), 4)

    def test_cancelled_ids_are_not_reused(self):
        order = self.service.place_order("regular", [self.item("mug", 1)])
        self.service.cancel_order(order["order_id"])
        self.assertEqual(self.service.place_order("regular", [self.item("mug", 1)])["order_id"],
                         "ORD-0002")


if __name__ == "__main__":
    unittest.main()
