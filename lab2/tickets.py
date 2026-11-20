"""Ticket booking with two data centres: London (primary) and Dublin (backup).

Time is simulated in milliseconds and starts at 0. Nothing is random, so the
same actions with the same settings always produce the same timeline.
"""

import heapq
from dataclasses import dataclass, asdict

LINK_DELAY = 50          # one-way delay between London and Dublin (ms)
LOCAL_DELAY = 25         # one-way delay between a customer and their data centre (ms)
BOOKING_TIME = 50        # time a data centre needs to record a booking (ms)
HEARTBEAT_EVERY = 1000   # London sends Dublin a heartbeat this often (ms)
ANSWER_WAIT = 2000       # how long a customer waits for an answer (ms)
FORWARD_WAIT = 1500      # how long Dublin waits for London to answer a passed-on booking (ms)
FAILURE_AT = 500         # when the chosen failure happens (ms)
PAUSE_LENGTH = 8000      # how long London stops when it pauses (ms)

SEATS = ["A1", "A2", "A3", "A4", "A5", "A6"]
FAILURES = ("none", "crash", "pause", "link")
TIMEOUTS = (3000, 10000)


@dataclass
class Settings:
    failure: str = "none"        # what goes wrong at FAILURE_AT
    timeout: int = 3000          # Dublin suspects London after this long without a heartbeat (ms)
    take_over: bool = True       # when Dublin suspects London: take over, or refuse bookings


class Site:
    def __init__(self, name, role):
        self.name = name
        self.role = role             # "primary" or "backup"
        self.state = "up"            # "up", "paused" or "crashed"
        self.seats = {}              # seat -> customer, as this site believes
        self.waiting = []            # messages that arrived while paused
        self.last_heartbeat = 0      # (Dublin only) when it last heard from London
        self.suspects = False        # (Dublin only) whether it thinks London has failed


class TicketSystem:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.reset()

    # ---------- bookkeeping ----------

    def reset(self):
        self.now = 0
        self.queue = []
        self.counter = 0
        self.timeline = []
        self.tickets = []            # tickets customers have been told they hold
        self.messages = []           # what customers are told: {time, customer, text}
        self.link_up = True
        self.london = Site("London", "primary")
        self.dublin = Site("Dublin", "backup")
        self.pending = {}            # request id -> waiting state
        self.next_request = 1
        self.schedule(0, self.send_heartbeat)
        self.schedule(self.settings.timeout, self.check_london, 0)
        failure = self.settings.failure
        if failure != "none":
            self.schedule(FAILURE_AT, self.start_failure, failure)

    def site(self, name):
        return self.london if name == "London" else self.dublin

    def other(self, site):
        return self.dublin if site is self.london else self.london

    def schedule(self, at, action, *args):
        self.counter += 1
        heapq.heappush(self.queue, (at, self.counter, action, args))

    def run_until(self, until):
        while self.queue and self.queue[0][0] <= until:
            at, _, action, args = heapq.heappop(self.queue)
            self.now = at
            action(*args)
        self.now = until

    def log(self, source, target, text, kind="message"):
        self.timeline.append({"time": self.now, "from": source, "to": target, "text": text, "kind": kind})

    def tell(self, customer, text):
        self.messages.append({"time": self.now, "customer": customer, "text": text})
        self.log(customer["site"], customer["name"], text)

    # ---------- failures ----------

    def start_failure(self, failure):
        if failure == "crash":
            self.london.state = "crashed"
            self.log("London", "", "London crashes and stops for good", "lost")
        elif failure == "pause":
            self.london.state = "paused"
            self.log("London", "", f"London stops responding for {PAUSE_LENGTH / 1000:g} s (it is still running)", "lost")
            self.schedule(self.now + PAUSE_LENGTH, self.end_pause)
        elif failure == "link":
            self.link_up = False
            self.log("Network", "", "the link between London and Dublin breaks; both data centres keep running", "lost")

    def end_pause(self):
        self.london.state = "up"
        self.log("London", "", "London carries on from where it stopped, still acting as primary", "event")
        waiting, self.london.waiting = self.london.waiting, []
        for handler, args in waiting:
            handler(*args)
        self.schedule(self.now, self.send_heartbeat)

    def heal_link(self):
        self.link_up = True
        self.log("Network", "", "the link between London and Dublin works again", "event")

    # ---------- messages ----------

    def deliver(self, site, handler, *args):
        """Hand a message to a site, unless it is crashed or paused."""
        if site.state == "crashed":
            return
        if site.state == "paused":
            site.waiting.append((handler, args))
            return
        handler(*args)

    def send_between_sites(self, source, target, text, handler, *args):
        self.log(source.name, target.name, text)
        if not self.link_up:
            self.log("Network", "", f"lost: {text}", "lost")
            return
        self.schedule(self.now + LINK_DELAY, self.deliver, target, handler, *args)

    # ---------- heartbeats and failure detection ----------

    def send_heartbeat(self):
        london = self.london
        if london.state != "up":
            return
        if self.link_up:
            self.schedule(self.now + LINK_DELAY, self.deliver, self.dublin, self.heartbeat_arrives)
        next_beat = (self.now // HEARTBEAT_EVERY + 1) * HEARTBEAT_EVERY
        self.schedule(next_beat, self.send_heartbeat)

    def heartbeat_arrives(self):
        dublin = self.dublin
        dublin.last_heartbeat = self.now
        if dublin.suspects:
            dublin.suspects = False
            if dublin.role == "primary":
                self.log("Dublin", "", "hears London again, but has already taken over: London and Dublin both act as primary", "warn")
            else:
                self.log("Dublin", "", "hears London again and goes back to passing bookings to London", "event")
        self.schedule(self.now + self.settings.timeout, self.check_london, self.now)

    def check_london(self, heard_at):
        dublin = self.dublin
        if dublin.last_heartbeat != heard_at or dublin.suspects or dublin.role == "primary":
            return
        dublin.suspects = True
        seconds = self.settings.timeout / 1000
        self.log("Dublin", "", f"no heartbeat from London for {seconds:g} s: Dublin decides London has failed", "timeout")
        if self.settings.take_over:
            dublin.role = "primary"
            self.log("Dublin", "", "takes over as primary and starts selling seats itself", "event")
        else:
            self.log("Dublin", "", "refuses bookings until it hears from London again", "event")

    # ---------- bookings ----------

    def book(self, customer, seat):
        """A customer asks their own data centre for a seat."""
        request = self.next_request
        self.next_request += 1
        site = self.site(customer["site"])
        self.pending[request] = {"customer": customer, "seat": seat, "answered": False}
        self.log(customer["name"], site.name, f"book seat {seat}")
        self.schedule(self.now + LOCAL_DELAY, self.deliver, site, self.request_arrives, site, request)
        self.schedule(self.now + ANSWER_WAIT, self.customer_gives_up, request)

    def customer_gives_up(self, request):
        state = self.pending[request]
        if state["answered"]:
            return
        customer = state["customer"]
        self.log(customer["name"], "", f"no answer within {ANSWER_WAIT / 1000:g} s", "timeout")
        self.messages.append({"time": self.now, "customer": customer,
                              "text": f"no answer from the site, please try again (seat {state['seat']})"})

    def answer_customer(self, site, request, text, booked=False):
        self.schedule(self.now + LOCAL_DELAY, self.customer_hears, request, text, booked)

    def customer_hears(self, request, text, booked):
        state = self.pending[request]
        customer = state["customer"]
        state["answered"] = True
        if booked:
            self.tickets.append({"time": self.now, "customer": customer["name"], "seat": state["seat"]})
        self.tell(customer, text)

    def request_arrives(self, site, request):
        state = self.pending[request]
        seat = state["seat"]
        if site.role == "primary":
            self.sell(site, request)
        elif site.suspects:
            self.log(site.name, "", f"refuses the booking of {seat}: it cannot reach London", "event")
            self.answer_customer(site, request, f"bookings are not available at the moment, please try later (seat {seat})")
        else:
            state["forwarded_at"] = self.now
            self.send_between_sites(site, self.other(site), f"booking request: {seat} for {state['customer']['name']}",
                                    self.forwarded_request_arrives, request)
            self.schedule(self.now + FORWARD_WAIT, self.forward_gives_up, site, request)

    def forwarded_request_arrives(self, request):
        self.sell(self.london, request, forwarded=True)

    def forward_gives_up(self, site, request):
        state = self.pending[request]
        if state.get("forward_answered"):
            return
        state["forward_answered"] = True
        self.log(site.name, "", f"no answer from London within {FORWARD_WAIT / 1000:g} s", "timeout")
        self.answer_customer(site, request, f"London is not responding, please try again (seat {state['seat']})")

    def sell(self, site, request, forwarded=False):
        state = self.pending[request]
        seat, name = state["seat"], state["customer"]["name"]
        done = self.now + BOOKING_TIME
        if seat in site.seats:
            text, booked = f"sorry, seat {seat} is already taken", False
        else:
            site.seats[seat] = name
            self.log(site.name, "", f"sells seat {seat} to {name}", "event")
            text, booked = f"booked: seat {seat} is yours", True
            self.schedule(done, self.copy_booking, site, seat, name)
        if forwarded:
            self.schedule(done, self.reply_to_dublin, request, text, booked)
        else:
            self.schedule(done, self.answer_customer, site, request, text, booked)

    def reply_to_dublin(self, request, text, booked):
        self.send_between_sites(self.london, self.dublin, f"reply for {self.pending[request]['customer']['name']}: {text}",
                                self.dublin_gets_reply, request, text, booked)

    def dublin_gets_reply(self, request, text, booked):
        state = self.pending[request]
        if state.get("forward_answered"):
            self.log("Dublin", "", f"reply from London arrived too late and is ignored ({text})", "late")
            return
        state["forward_answered"] = True
        self.answer_customer(self.dublin, request, text, booked)

    def copy_booking(self, site, seat, name):
        target = self.other(site)
        self.send_between_sites(site, target, f"copy: seat {seat} sold to {name}", self.receive_copy, target, site, seat, name)

    def receive_copy(self, site, sender, seat, name):
        holder = site.seats.get(seat)
        if holder is None:
            site.seats[seat] = name
        elif holder != name:
            self.log(site.name, "", f"{sender.name} says seat {seat} went to {name}, but here it went to {holder}", "warn")

    # ---------- what the page shows ----------

    def state(self):
        def site_view(s):
            return {"name": s.name, "role": s.role, "state": s.state, "seats": s.seats,
                    "suspects": s.suspects, "last_heartbeat": s.last_heartbeat}
        return {
            "now": self.now,
            "settings": asdict(self.settings),
            "link_up": self.link_up,
            "sites": [site_view(self.london), site_view(self.dublin)],
            "tickets": self.tickets,
            "messages": [{"time": m["time"], "customer": m["customer"]["name"], "text": m["text"]} for m in self.messages],
            "timeline": sorted(self.timeline, key=lambda e: e["time"]),
        }


def replay(system, recording):
    """Run a recorded set of events with the system's current settings."""
    system.settings.failure = "none"
    system.reset()
    customers = {c["name"]: c for c in recording["customers"]}
    for event in recording["events"]:
        if event["type"] == "book":
            system.schedule(event["time"], system.book, customers[event["customer"]], event["seat"])
        else:
            system.schedule(event["time"], {"crash": lambda s=system: s.start_failure("crash"),
                                            "pause": lambda s=system: s.start_failure("pause"),
                                            "link": lambda s=system: s.start_failure("link"),
                                            "heal": system.heal_link}[event["type"]])
    system.run_until(recording["end"])
