"""Tests for the individual commands (cli.py) and the interactive menu (menu.py)."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest import mock

from supplydesk import cli
from supplydesk.menu import run_menu
from tests.helpers import TempStateTestCase


class CommandTests(TempStateTestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                status = cli.main(["--data", str(self.path), *args])
            except SystemExit as exit_:  # argparse rejects bad options this way
                status = exit_.code
        return status, out.getvalue(), err.getvalue()

    def test_quote_command_prints_json_with_defaults(self):
        status, out, _ = self.run_cli("quote", "--item", "notebook:2")
        self.assertEqual(status, 0)
        result = json.loads(out)
        self.assertEqual((result["customer_type"], result["fulfillment"]), ("regular", "pickup"))
        self.assertEqual(result["total_cents"], 1000)
        self.assertFalse(self.path.exists())

    def test_place_show_cancel_round_trip(self):
        status, out, _ = self.run_cli("place", "--customer", "student", "--fulfillment",
                                      "delivery", "--item", "hoodie:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 7800)
        status, out, _ = self.run_cli("show", "ORD-0001")
        self.assertEqual((status, json.loads(out)["status"]), (0, "placed"))
        status, out, _ = self.run_cli("cancel", "ORD-0001")
        self.assertEqual((status, json.loads(out)["status"]), (0, "cancelled"))
        status, out, _ = self.run_cli("orders")
        self.assertEqual([o["order_id"] for o in json.loads(out)], ["ORD-0001"])

    def test_service_errors_exit_nonzero_with_message(self):
        status, out, err = self.run_cli("place", "--item", "laptop:1")
        self.assertNotEqual(status, 0)
        self.assertEqual(out, "")
        self.assertIn("Error:", err)
        self.assertFalse(self.path.exists())

    def test_parser_rejects_bad_options(self):
        for args in (("quote", "--fulfillment", "courier", "--item", "mug:1"),
                     ("quote", "--customer", "staff", "--item", "mug:1"),
                     ("quote", "--item", "mug:two"),
                     ("quote",)):
            with self.subTest(args=args):
                status, _, _ = self.run_cli(*args)
                self.assertNotEqual(status, 0)


class MenuTests(TempStateTestCase):
    def run_menu_with(self, *answers):
        out = io.StringIO()
        # After the scripted answers, input() raises EOFError like a closed terminal.
        with mock.patch("builtins.input", side_effect=[*answers, EOFError()]), \
                redirect_stdout(out):
            status = run_menu(self.service)
        return status, out.getvalue()

    def test_quote_uses_blank_defaults(self):
        status, out = self.run_menu_with("2", "", "notebook", "2", "", "", "0")
        self.assertEqual(status, 0)
        self.assertIn("Customer: regular | Fulfillment: pickup", out)
        self.assertIn("Total: $10.00", out)
        self.assertFalse(self.path.exists())

    def test_declining_placement_saves_nothing(self):
        _, out = self.run_menu_with("3", "student", "hoodie", "2", "", "delivery", "n", "0")
        self.assertIn("Total: $78.00", out)
        self.assertIn("Order not placed.", out)
        self.assertFalse(self.path.exists())

    def test_confirmed_placement_is_saved(self):
        _, out = self.run_menu_with("3", "", "mug", "1", "", "", "y", "0")
        self.assertIn("ORD-0001 - placed", out)
        self.assertEqual(self.service.get_order("ORD-0001")["total_cents"], 1500)

    def test_bad_quantity_asks_again_and_errors_return_to_menu(self):
        _, out = self.run_menu_with("2", "", "mug", "two", "mug", "1", "", "courier", "0")
        self.assertIn("Please enter a whole number", out)
        self.assertIn("Error:", out)
        self.assertIn("Goodbye.", out)

    def test_end_of_input_exits_cleanly(self):
        status, out = self.run_menu_with()
        self.assertEqual(status, 0)
        self.assertIn("Goodbye.", out)


if __name__ == "__main__":
    unittest.main()
