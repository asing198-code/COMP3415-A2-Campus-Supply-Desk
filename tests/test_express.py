"""CR-01: express delivery (flat 1,200 cents, never waived)."""

from contextlib import redirect_stdout
import io
import json
import unittest
from unittest import mock

from supplydesk import cli
from supplydesk.menu import run_menu
from supplydesk.service import OrderService
from tests.helpers import TempStateTestCase


def totals(result):
    return (result["subtotal_cents"], result["discount_cents"],
            result["delivery_cents"], result["total_cents"])


class ExpressPricingTests(TempStateTestCase):
    def test_cr01_examples(self):
        cases = [
            ("regular", [self.item("notebook", 2)], (1000, 0, 1200, 2200)),
            ("student", [self.item("hoodie", 2)], (8000, 800, 1200, 8400)),
            ("regular", [self.item("hoodie", 3)], (12000, 0, 1200, 13200)),
        ]
        for customer, items, expected in cases:
            with self.subTest(customer=customer, items=items):
                self.assertEqual(totals(self.service.quote(customer, items, "express")), expected)

    def test_express_is_never_waived_but_standard_still_is(self):
        items = [self.item("hoodie", 3)]  # 12,000: over the free-delivery threshold
        self.assertEqual(self.service.quote("regular", items, "delivery")["delivery_cents"], 0)
        self.assertEqual(self.service.quote("regular", items, "express")["delivery_cents"], 1200)
        self.assertEqual(self.service.quote("regular", items, "pickup")["delivery_cents"], 0)

    def test_student_discount_unchanged_and_excludes_express_fee(self):
        # 10 notebooks = 5,000: discount threshold boundary; discount is 10% of 5,000, not of 6,200.
        quote = self.service.quote("student", [self.item("notebook", 10)], "express")
        self.assertEqual(totals(quote), (5000, 500, 1200, 5700))
        below = self.service.quote("student", [self.item("notebook", 9)], "express")
        self.assertEqual(totals(below), (4500, 0, 1200, 5700))

    def test_other_fulfillment_values_remain_invalid(self):
        for fulfillment in ("Express", "EXPRESS", " express", "courier", "rush", ""):
            with self.subTest(fulfillment=fulfillment):
                with self.assertRaises(ValueError):
                    self.service.quote("regular", [self.item("mug", 1)], fulfillment)
                with self.assertRaises(ValueError):
                    self.service.place_order("regular", [self.item("mug", 1)], fulfillment)
        self.assertFalse(self.path.exists())

    def test_express_keeps_existing_validation_and_stock_rules(self):
        for items in ([], [self.item("hoodie", 6)], [self.item("bag", 3), self.item("bag", 2)],
                      [self.item("mug", True)]):
            with self.subTest(items=items):
                with self.assertRaises(ValueError):
                    self.service.place_order("student", items, "express")
        self.assertFalse(self.path.exists())


class ExpressOrderLifecycleTests(TempStateTestCase):
    def test_quote_matches_placed_order(self):
        items = [self.item("hoodie", 2), self.item("mug", 1)]
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")
        self.assertEqual({k: v for k, v in order.items() if k not in ("order_id", "status")},
                         quote)
        self.assertEqual(order["fulfillment"], "express")

    def test_express_order_survives_reopen_and_cancel(self):
        self.service.place_order("regular", [self.item("notebook", 1)])  # ORD-0001
        order = self.service.place_order("student", [self.item("hoodie", 2)], "express")
        self.assertEqual(order["order_id"], "ORD-0002")
        self.assertEqual(self.stock("hoodie"), 3)

        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order("ORD-0002"), order)

        cancelled = reopened.cancel_order("ORD-0002")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual({k: v for k, v in cancelled.items() if k != "status"},
                         {k: v for k, v in order.items() if k != "status"})
        self.assertEqual(self.stock("hoodie"), 5)

        again = OrderService(self.path)
        self.assertEqual(again.cancel_order("ORD-0002"), cancelled)  # repeat changes nothing
        self.assertEqual(self.stock("hoodie"), 5)
        self.assertEqual([o["fulfillment"] for o in again.list_orders()], ["pickup", "express"])
        self.assertEqual(again.place_order("regular", [self.item("mug", 1)], "express")["order_id"],
                         "ORD-0003")


class ExpressInterfaceTests(TempStateTestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            status = cli.main(["--data", str(self.path), *args])
        return status, out.getvalue()

    def test_cli_quote_example_from_cr01(self):
        status, out = self.run_cli("quote", "--customer", "student", "--fulfillment", "express",
                                   "--item", "hoodie:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 8400)

    def test_cli_place_and_show_express(self):
        self.run_cli("place", "--fulfillment", "express", "--item", "notebook:2")
        status, out = self.run_cli("show", "ORD-0001")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["fulfillment"], "express")
        self.assertEqual(json.loads(out)["total_cents"], 2200)

    def test_cli_help_mentions_express(self):
        for command in ("quote", "place"):
            with self.subTest(command=command):
                out = io.StringIO()
                with redirect_stdout(out), self.assertRaises(SystemExit):
                    cli.main([command, "--help"])
                self.assertIn("express", out.getvalue())

    def test_menu_prompt_lists_express_and_quotes_it(self):
        prompts, out = [], io.StringIO()
        answers = iter(["2", "student", "hoodie", "2", "", "express", "0"])

        def fake_input(prompt=""):
            prompts.append(prompt)
            return next(answers)

        with mock.patch("builtins.input", side_effect=fake_input), redirect_stdout(out):
            run_menu(self.service)
        self.assertTrue(any("express" in p for p in prompts if p.startswith("Fulfillment")))
        self.assertIn("Customer: student | Fulfillment: express", out.getvalue())
        self.assertIn("Delivery: $12.00", out.getvalue())
        self.assertIn("Total: $84.00", out.getvalue())

    def test_menu_blank_fulfillment_still_defaults_to_pickup(self):
        out = io.StringIO()
        answers = ["2", "", "mug", "1", "", "", "0"]
        with mock.patch("builtins.input", side_effect=answers), redirect_stdout(out):
            run_menu(self.service)
        self.assertIn("Customer: regular | Fulfillment: pickup", out.getvalue())


if __name__ == "__main__":
    unittest.main()
