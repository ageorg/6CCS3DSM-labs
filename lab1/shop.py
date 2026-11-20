"""The online shop: Shop, Stock and Payment, talking over a simulated network.

Time is simulated in milliseconds and starts at 0. Nothing is random, so the
same orders with the same settings always produce the same timeline.
"""

from dataclasses import dataclass, field, asdict

NETWORK_DELAY = 50     # one-way delay between two services (ms)
STOCK_TIME = 100       # time Stock needs to reserve the items (ms)
PAYMENT_TIME = 200     # time Payment needs to charge a card (ms)
SLOW_PAUSE = 6000      # extra time Payment takes when it is slow (ms)

TIMEOUT = 2000         # how long the shop waits for a reply from Payment (ms)
MAX_ATTEMPTS = 3       # how many charge requests the shop sends at most
RETRY_DELAY = 500      # how long the shop waits before trying again (ms)
CHECK_DELAY = 5000     # how long the shop waits before asking about a pending order (ms)
MAX_CHECKS = 3
GAP_BETWEEN_ORDERS = 1000

CATALOGUE = {
    "Headphones": 59.00,
    "Book": 12.50,
    "Desk lamp": 34.00,
}

FAILURES = ("none", "lose_request", "lose_reply", "slow")


@dataclass
class Settings:
    failure: str = "none"        # what goes wrong on the first charge request of each order
    use_key: bool = False        # send an idempotency key with every charge request
    mark_pending: bool = False   # if no attempt gets a reply, mark the order pending


@dataclass
class Conditions:
    """What the network and Payment do during one charge attempt."""
    lose_request: bool = False
    lose_reply: bool = False
    payment_pause: int = 0


@dataclass
class Order:
    id: int
    customer: str
    items: list
    total: float
    status: str = "in progress"
    key: str = ""

    def description(self):
        return ", ".join(self.items)


class PaymentService:
    def __init__(self):
        self.charges = []   # what customers see on their bank statements
        self.keys = {}      # idempotency key -> time the charge was finished

    def handle(self, customer, description, amount, key, arrives, pause):
        """Handle a charge request arriving at time `arrives`.

        Returns (time the reply is sent, result), where result is
        "charged", "already_charged" or "in_progress".
        """
        if key and key in self.keys:
            if arrives < self.keys[key]:
                return arrives, "in_progress"
            return arrives, "already_charged"    # do not charge again

        finished = arrives + PAYMENT_TIME + pause
        self.charges.append({"time": finished, "customer": customer,
                             "items": description, "amount": amount})
        if key:
            self.keys[key] = finished             # remember the key
        return finished, "charged"

    def was_charged(self, key, now):
        """Answer a question from the shop: "yes", "no" or "still processing"."""
        if key not in self.keys:
            return "no"
        if now < self.keys[key]:
            return "still processing"
        return "yes"


class Shop:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.reset()

    def reset(self):
        self.payment = PaymentService()
        self.reservations = []
        self.orders = []
        self.timeline = []
        self.clock = 0
        self.current_order = None

    def log(self, time, source, target, text, kind="message"):
        self.timeline.append({"time": time, "from": source, "to": target, "text": text,
                              "kind": kind, "order": self.current_order})

    def checkout(self, customer, items, conditions=None):
        if conditions is None:
            conditions = self.conditions_from_settings()

        total = round(sum(CATALOGUE[item] for item in items), 2)
        order = Order(len(self.orders) + 1, customer, list(items), total)
        self.orders.append(order)
        self.current_order = order.id

        now = self.clock
        self.log(now, customer, "Shop", f"pays £{total:.2f} for {order.description()}, order #{order.id}")
        now = self.reserve_stock(order, now)
        now = self.pay(order, now, conditions)

        last_event = max(event["time"] for event in self.timeline)
        self.clock = max(now, last_event) + GAP_BETWEEN_ORDERS
        return order

    def conditions_from_settings(self):
        failure = self.settings.failure
        first_attempt = Conditions(
            lose_request=failure == "lose_request",
            lose_reply=failure == "lose_reply",
            payment_pause=SLOW_PAUSE if failure == "slow" else 0,
        )
        return [first_attempt]

    def reserve_stock(self, order, now):
        self.log(now, "Shop", "Stock", f"reserve {order.description()}")
        self.reservations.append({"time": now + NETWORK_DELAY + STOCK_TIME,
                                  "customer": order.customer, "items": order.description()})
        now += NETWORK_DELAY + STOCK_TIME + NETWORK_DELAY
        self.log(now, "Stock", "Shop", "reserved")
        return now

    def pay(self, order, now, conditions):
        if self.settings.use_key:
            order.key = f"order-{order.id}"      # the same key on every attempt

        for attempt in range(1, MAX_ATTEMPTS + 1):
            cond = conditions[attempt - 1] if attempt <= len(conditions) else Conditions()
            paid, now = self.call_payment(order, attempt, cond, now)
            if paid:
                order.status = "paid"
                self.log(now, "Shop", order.customer, "payment successful, thank you!")
                return now
            if attempt < MAX_ATTEMPTS:
                now += RETRY_DELAY               # wait a little, then try again

        if self.settings.mark_pending:
            order.status = "pending"             # we do not know, so do not guess
            self.log(now, "Shop", order.customer, "we are checking your payment and will email you")
            return self.check_later(order, now)

        order.status = "failed"
        self.log(now, "Shop", order.customer, "payment failed, please try again")
        return now

    def call_payment(self, order, attempt, cond, sent):
        """One attempt to charge the customer. Returns (paid, time)."""
        deadline = sent + TIMEOUT
        with_key = f", key {order.key}" if order.key else ""
        self.log(sent, "Shop", "Payment",
                 f"charge {order.customer} £{order.total:.2f} (attempt {attempt}{with_key})")

        if cond.lose_request:
            self.log(sent + NETWORK_DELAY, "Network", "", f"attempt {attempt} lost on the way to Payment", "lost")
            return self.give_up(attempt, deadline)

        arrives = sent + NETWORK_DELAY
        reply_sent, result = self.payment.handle(order.customer, order.description(), order.total,
                                                 order.key, arrives, cond.payment_pause)
        if result == "charged":
            if cond.payment_pause:
                self.log(arrives, "Payment", "", f"running slowly: this charge takes {cond.payment_pause / 1000:g} s longer", "event")
            self.log(reply_sent, "Payment", "", f"charged {order.customer} £{order.total:.2f}", "event")
            reply = "paid"
        elif result == "already_charged":
            self.log(arrives, "Payment", "", f"key {order.key} already charged: no new charge", "event")
            reply = "paid, already charged"
        else:
            self.log(arrives, "Payment", "", f"key {order.key} is still being processed", "event")
            reply = "still processing, try again later"

        reply_arrives = reply_sent + NETWORK_DELAY
        if cond.lose_reply:
            self.log(reply_arrives, "Network", "", f"reply to attempt {attempt} lost on the way to Shop", "lost")
            return self.give_up(attempt, deadline)

        if reply_arrives > deadline:
            self.give_up(attempt, deadline)
            self.log(reply_arrives, "Payment", "Shop",
                     f"{reply} (attempt {attempt}): arrived after the shop stopped waiting, ignored", "late")
            return False, deadline

        self.log(reply_arrives, "Payment", "Shop", f"{reply} (attempt {attempt})")
        return result != "in_progress", reply_arrives

    def give_up(self, attempt, deadline):
        self.log(deadline, "Shop", "", f"no reply to attempt {attempt} within {TIMEOUT / 1000:g} s", "timeout")
        return False, deadline

    def check_later(self, order, now):
        """Ask Payment whether a pending order was charged, using its key."""
        if not order.key:
            self.log(now, "Shop", "", "no key was sent, so the shop cannot ask Payment about this order", "event")
            return now

        for _ in range(MAX_CHECKS):
            now += CHECK_DELAY
            self.log(now, "Shop", "Payment", f"was {order.key} charged?")
            answer = self.payment.was_charged(order.key, now + NETWORK_DELAY)
            now += 2 * NETWORK_DELAY
            self.log(now, "Payment", "Shop", f"{order.key}: {answer}")

            if answer == "still processing":
                continue
            if answer == "yes":
                order.status = "paid"
                self.log(now, "Shop", order.customer, "your payment went through, thank you!")
            else:
                order.status = "failed"
                self.log(now, "Shop", order.customer, "your payment did not go through, please try again")
            return now

        self.log(now, "Shop", "", "still no answer from Payment, the order stays pending", "event")
        return now

    def state(self):
        orders = []
        for order in self.orders:
            data = asdict(order)
            data["description"] = order.description()
            orders.append(data)
        return {
            "settings": asdict(self.settings),
            "orders": orders,
            "reservations": self.reservations,
            "charges": sorted(self.payment.charges, key=lambda c: c["time"]),
            "timeline": sorted(self.timeline, key=lambda e: e["time"]),
        }


def replay(shop, orders):
    """Run a list of recorded orders, with the shop's current settings."""
    shop.reset()
    for entry in orders:
        conditions = [Conditions(**attempt) for attempt in entry.get("attempts", [])]
        shop.checkout(entry["customer"], entry["items"], conditions)
