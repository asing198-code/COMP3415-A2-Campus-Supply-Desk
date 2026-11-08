"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore

# Allowed request options, shared with cli.py and menu.py.
CUSTOMER_TYPES = ("regular", "student")
FULFILLMENT_OPTIONS = ("pickup", "delivery", "express")

# Pricing rules. All money values are integer Canadian cents.
STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000
STUDENT_DISCOUNT_PERCENT = 10
DELIVERY_FEE_CENTS = 600
FREE_DELIVERY_THRESHOLD_CENTS = 10000  # applies to standard delivery only
EXPRESS_FEE_CENTS = 1200  # CR-01: flat fee, never waived

# Request limits and order numbering.
MIN_QUANTITY = 1
MAX_QUANTITY = 99
ORDER_ID_PREFIX = "ORD-"
ORDER_NUMBER_DIGITS = 4


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        return self._price_request(state, customer_type, items, fulfillment)

    def place_order(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        priced = self._price_request(state, customer_type, items, fulfillment)
        order = {"order_id": self._format_order_id(state["next_order_number"]),
                 "status": "placed", **priced}
        for line in order["items"]:
            self._find_product(state, line["product_id"])["stock"] -= line["quantity"]
        state["next_order_number"] += 1
        state["orders"].append(order)
        self.store.save(state)
        return order

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        return self._find_order(self.store.load(), order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = self._find_order(state, order_id)
        if order["status"] == "cancelled":
            return order  # already cancelled: stock was restored the first time
        for line in order["items"]:
            self._find_product(state, line["product_id"])["stock"] += line["quantity"]
        order["status"] = "cancelled"
        self.store.save(state)
        return order

    # Validation and pricing shared by quote() and place_order().

    def _price_request(self, state, customer_type, items, fulfillment):
        """Validate a request against current stock and return its priced details."""
        self._validate_options(customer_type, fulfillment, items)
        requested = {}  # product_id -> units requested so far, across duplicate lines
        lines = [self._price_line(state, item, requested) for item in items]
        subtotal = sum(line["line_total_cents"] for line in lines)
        discount = self._discount_cents(customer_type, subtotal)
        delivery = self._delivery_cents(fulfillment, subtotal - discount)
        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": lines,
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "delivery_cents": delivery,
            "total_cents": subtotal - discount + delivery,
        }

    @staticmethod
    def _validate_options(customer_type, fulfillment, items):
        if customer_type not in CUSTOMER_TYPES:
            raise ValueError("Customer type must be regular or student.")
        if fulfillment not in FULFILLMENT_OPTIONS:
            raise ValueError("Fulfillment must be pickup, delivery, or express.")
        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")

    def _price_line(self, state, item, requested):
        if not isinstance(item, dict):
            raise ValueError("Each item must contain a product_id and quantity.")
        product = self._find_product(state, item.get("product_id"))
        if product is None:
            raise ValueError("Unknown product.")
        quantity = item.get("quantity")
        if type(quantity) is not int or not MIN_QUANTITY <= quantity <= MAX_QUANTITY:
            raise ValueError("Quantity must be an integer from 1 to 99.")
        product_id = product["product_id"]
        requested[product_id] = requested.get(product_id, 0) + quantity
        if requested[product_id] > product["stock"]:
            raise ValueError("Not enough stock for " + product_id + ".")
        return {
            "product_id": product["product_id"],
            "name": product["name"],
            "unit_price_cents": product["unit_price_cents"],
            "quantity": quantity,
            "line_total_cents": product["unit_price_cents"] * quantity,
        }

    @staticmethod
    def _discount_cents(customer_type, subtotal):
        if customer_type == "student" and subtotal >= STUDENT_DISCOUNT_THRESHOLD_CENTS:
            # Integer percentage, rounded to the nearest cent with half a cent rounded up.
            return (subtotal * STUDENT_DISCOUNT_PERCENT + 50) // 100
        return 0

    @staticmethod
    def _delivery_cents(fulfillment, discounted_subtotal):
        if fulfillment == "express":
            return EXPRESS_FEE_CENTS
        if fulfillment == "delivery" and discounted_subtotal < FREE_DELIVERY_THRESHOLD_CENTS:
            return DELIVERY_FEE_CENTS
        return 0

    # Lookups.

    @staticmethod
    def _find_product(state, product_id):
        for product in state["catalog"]:
            if product["product_id"] == product_id:
                return product
        return None

    @staticmethod
    def _find_order(state, order_id):
        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    @staticmethod
    def _format_order_id(number):
        return ORDER_ID_PREFIX + str(number).zfill(ORDER_NUMBER_DIGITS)
