"""A shared trip planner kept on two servers: London and New York.

Time is simulated in milliseconds and starts at 0. Nothing is random, so the
same edits with the same settings always produce the same timeline.
"""

import heapq
from dataclasses import dataclass, asdict

SYNC_DELAY = 1500        # time for an edit to reach the other server (ms)
START_OF_DAY = 14 * 3600 * 1000   # wall-clock time at the start of a run: 14:00:00
SKEW = -3000             # how far New York's clock is off when it is wrong (ms)

SERVERS = ["London", "New York"]
FIELDS = {"time": ["09:30", "10:00", "11:00"], "place": ["Library", "Café", "Park"]}
INITIAL = {"time": "09:30", "place": "Library"}
FAILURES = ("none", "skew")
STAMPS = ("clock", "lamport", "vector")


@dataclass
class Settings:
    failure: str = "none"     # "none", or "skew": New York's clock is 3 s behind
    stamps: str = "clock"     # what each edit is stamped with


@dataclass
class Version:
    value: str
    author: str
    stamp: object             # wall-clock ms, a Lamport number, or a vector [London, New York]
    origin: str = "London"    # the server where the edit was made

    def show(self, stamps):
        return f"{self.value} ({self.author}, {format_stamp(self.stamp, stamps)})"


def format_clock(ms):
    seconds, ms = divmod(int(ms), 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def format_stamp(stamp, stamps):
    if stamps == "clock":
        return format_clock(stamp)
    if stamps == "lamport":
        return f"Lamport {stamp}"
    return f"vector ⟨{stamp[0]}, {stamp[1]}⟩"


class Server:
    def __init__(self, name, index, skew):
        self.name = name
        self.index = index
        self.skew = skew
        self.lamport = 0
        self.vector = [0, 0]
        self.fields = {}      # field -> list of versions (more than one means a conflict)

    def clock(self, now):
        return START_OF_DAY + now + self.skew


def later(a, b):
    """Last-writer-wins: is version a later than version b?"""
    if a.stamp != b.stamp:
        return a.stamp > b.stamp
    return SERVERS.index(a.origin) > SERVERS.index(b.origin)   # a tie goes to New York


def before(a, b):
    """Vector clocks: a happened before b."""
    return all(x <= y for x, y in zip(a, b)) and a != b


class Planner:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.reset()

    def reset(self):
        self.now = 0
        self.queue = []
        self.counter = 0
        self.timeline = []
        skew = SKEW if self.settings.failure == "skew" else 0
        self.servers = {"London": Server("London", 0, 0), "New York": Server("New York", 1, skew)}
        for server in self.servers.values():
            for field, value in INITIAL.items():
                server.fields[field] = [self.initial_version(value)]

    def initial_version(self, value):
        stamps = self.settings.stamps
        stamp = {"clock": START_OF_DAY - 60000, "lamport": 0, "vector": [0, 0]}[stamps]
        return Version(value, "organiser", stamp, "London")

    def schedule(self, at, action, *args):
        self.counter += 1
        heapq.heappush(self.queue, (at, self.counter, action, args))

    def run_until(self, until):
        while self.queue and self.queue[0][0] <= until:
            at, _, action, args = heapq.heappop(self.queue)
            self.now = at
            action(*args)
        self.now = until

    def log(self, source, target, text, kind="message", field=None):
        self.timeline.append({"time": self.now, "from": source, "to": target, "text": text,
                              "kind": kind, "field": field})

    # ---------- stamping ----------

    def stamp_edit(self, server):
        stamps = self.settings.stamps
        if stamps == "clock":
            return server.clock(self.now)
        if stamps == "lamport":
            server.lamport += 1
            return server.lamport
        server.vector[server.index] += 1
        return list(server.vector)

    def note_receipt(self, server, stamp):
        stamps = self.settings.stamps
        if stamps == "lamport":
            server.lamport = max(server.lamport, stamp) + 1
        elif stamps == "vector":
            server.vector = [max(a, b) for a, b in zip(server.vector, stamp)]
            server.vector[server.index] += 1

    # ---------- edits ----------

    def edit(self, user, field, value):
        """A user changes a field through their own server."""
        server = self.servers[user["server"]]
        stamp = self.stamp_edit(server)
        version = Version(value, user["name"], stamp, server.name)
        stamps = self.settings.stamps
        self.log(user["name"], server.name, f"set {field} to {value}", field=field)
        self.log(server.name, "", f"stamps the edit: {format_stamp(stamp, stamps)}", "event", field)
        self.store(server, field, version, local=True)
        other = self.servers["New York" if server.name == "London" else "London"]
        self.log(server.name, other.name, f"update: {field} = {version.show(stamps)}", field=field)
        self.schedule(self.now + SYNC_DELAY, self.receive, other, field, version)

    def receive(self, server, field, version):
        self.note_receipt(server, version.stamp)
        self.store(server, field, version, local=False)

    def store(self, server, field, version, local):
        stamps = self.settings.stamps
        current = server.fields[field]
        where = server.name

        if stamps == "vector":
            if local:
                server.fields[field] = [version]       # the user has seen every current version
                if len(current) > 1:
                    self.log(where, "", f"{field}: conflict resolved, keeps {version.value}", "event", field)
                return
            if any(before(version.stamp, c.stamp) or version.stamp == c.stamp for c in current):
                self.log(where, "", f"{field}: update is older than what it has, ignored", "event", field)
                return
            newer = [c for c in current if not before(c.stamp, version.stamp)]
            server.fields[field] = sorted(newer + [version], key=lambda v: SERVERS.index(v.origin))
            if newer:
                shown = " and ".join(v.value for v in server.fields[field])
                self.log(where, "", f"{field}: neither version came first, keeps both as a conflict: {shown}", "warn", field)
            else:
                self.log(where, "", f"{field}: update is newer, now {version.value}", "event", field)
            return

        existing = current[0]
        if later(version, existing):
            server.fields[field] = [version]
            if not local:
                self.log(where, "", f"{field}: update is newer, now {version.value}", "event", field)
        else:
            whose = f"{version.author}'s edit" if local else "update"
            self.log(where, "", f"{field}: {whose} ({version.value}) has an earlier timestamp than "
                                f"{existing.value} ({format_stamp(existing.stamp, stamps)}), so it is discarded", "warn", field)

    # ---------- what the page shows ----------

    def state(self):
        stamps = self.settings.stamps
        servers = []
        for server in self.servers.values():
            servers.append({
                "name": server.name,
                "clock": format_clock(server.clock(self.now)),
                "lamport": server.lamport,
                "vector": server.vector,
                "fields": {f: [{"value": v.value, "author": v.author, "stamp": format_stamp(v.stamp, stamps)}
                               for v in versions] for f, versions in server.fields.items()},
            })
        return {
            "now": self.now,
            "settings": asdict(self.settings),
            "servers": servers,
            "timeline": sorted(self.timeline, key=lambda e: e["time"]),
        }


def replay(planner, recording):
    """Run a recorded set of edits with the planner's current settings."""
    planner.settings.failure = recording.get("failure", "none")
    planner.reset()
    users = {u["name"]: u for u in recording["users"]}
    for e in recording["edits"]:
        planner.schedule(e["time"], planner.edit, users[e["user"]], e["field"], e["value"])
    planner.run_until(recording["end"])
