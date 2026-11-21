"""A team chat kept on three servers: London, Paris and Singapore.

Every message posted on one server is broadcast to the other two. Each server
decides when to deliver a message it has received, that is, when to show it in
the chat. Until then the message waits in the server's buffer.

Time is simulated in milliseconds and starts at 0. Nothing is random, so the
same posts with the same settings always produce the same timeline.
"""

import heapq
from dataclasses import dataclass, asdict, field

DELAY = 1500          # time for a message to go from one server to another (ms)
RESEND_AFTER = 3000   # a lost message is sent again after this long (ms)
CRASH_AT = 3000       # when London crashes, if it does (ms)

SERVERS = ["London", "Paris", "Singapore"]
SEQUENCER = "London"
INITIAL_TOPIC = "Team chat"

FAILURES = ("none", "lost", "crash")
DELIVERY = ("receipt", "fifo", "causal", "total")


@dataclass
class Settings:
    failure: str = "none"      # "none"; "lost": London's first message to Singapore is lost; "crash": London crashes
    delivery: str = "receipt"  # when a server delivers a message it has received


@dataclass
class Post:
    id: str                    # "L1" is the first message posted on London, "P2" the second on Paris
    origin: str                # the server it was posted on
    author: str
    kind: str                  # "chat" or "topic"
    text: str
    seq: int = 0               # FIFO: how many messages its server had broadcast before this one
    deps: list = field(default_factory=list)   # causal: what its server had delivered when it was sent
    number: int = 0            # total order: the number the sequencer gave it


def vector(v):
    return "⟨" + ", ".join(str(x) for x in v) + "⟩"


class Server:
    def __init__(self, name):
        self.name = name
        self.index = SERVERS.index(name)
        self.crashed = False
        self.posted = 0                    # how many messages have been posted here, for the ids
        self.send_seq = 0                  # FIFO and causal: how many messages this server has broadcast
        self.delivered = [0, 0, 0]         # FIFO and causal: how many delivered from each server
        self.next_number = 1               # total order: the number to deliver next
        self.next_to_give = 1              # total order, sequencer only: the number to give out next
        self.buffer = []                   # received but not yet delivered
        self.log = []                      # delivered, in order
        self.waiting = []                  # total order: posted here, sent to the sequencer, not yet delivered here
        self.topic = INITIAL_TOPIC


class Chat:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.lost = [1]                    # which of London's messages to Singapore are lost (1 = the first)
        self.reset()

    def reset(self):
        self.now = 0
        self.queue = []
        self.counter = 0
        self.timeline = []
        self.servers = {name: Server(name) for name in SERVERS}
        self.sent_london_singapore = 0
        if self.settings.failure == "crash":
            self.schedule(CRASH_AT, self.crash, self.servers["London"])

    def schedule(self, at, action, *args):
        self.counter += 1
        heapq.heappush(self.queue, (at, self.counter, action, args))

    def run_until(self, until):
        while self.queue and self.queue[0][0] <= until:
            at, _, action, args = heapq.heappop(self.queue)
            self.now = at
            action(*args)
        self.now = until

    def log(self, source, target, text, kind="message", servers=()):
        self.timeline.append({"time": self.now, "from": source, "to": target, "text": text,
                              "kind": kind, "servers": list(servers)})

    def describe(self, post):
        """What a message carries, as the timeline shows it."""
        mode = self.settings.delivery
        if mode == "fifo":
            return f"{post.id}, seq {post.seq}"
        if mode == "causal":
            return f"{post.id}, deps {vector(post.deps)}"
        if mode == "total" and post.number:
            return f"#{post.number} ({post.id})"
        return post.id

    # ---------- the network ----------

    def send(self, source, target, action, post, text):
        """Send a message over the link from one server to another."""
        if source.name == "London" and target.name == "Singapore":
            self.sent_london_singapore += 1
            if self.settings.failure == "lost" and self.sent_london_singapore in self.lost:
                self.log(source.name, target.name, text, servers=[source.name, target.name])
                self.log("Network", "", f"{post.id} to Singapore is lost", "lost", [source.name, target.name])
                self.schedule(self.now + RESEND_AFTER, self.resend, source, target, action, post, text)
                return
        self.log(source.name, target.name, text, servers=[source.name, target.name])
        self.schedule(self.now + DELAY, self.arrive, target, action, post)

    def resend(self, source, target, action, post, text):
        if source.crashed:
            return
        self.log(source.name, target.name, f"{text} (sent again)", servers=[source.name, target.name])
        self.schedule(self.now + DELAY, self.arrive, target, action, post)

    def arrive(self, server, action, post):
        if server.crashed:
            self.log("Network", "", f"{post.id} reaches {server.name}, which has crashed", "lost", [server.name])
            return
        action(server, post)

    def crash(self, server):
        server.crashed = True
        self.log(server.name, "", "crashes", "warn", [server.name])

    # ---------- posting ----------

    def post(self, user, kind, text):
        """A user posts a message or changes the topic through their own server."""
        server = self.servers[user["server"]]
        if server.crashed:
            return
        server.posted += 1
        post = Post(f"{server.name[0]}{server.posted}", server.name, user["name"], kind, text)
        what = f'"{text}"' if kind == "chat" else f"sets the topic to {text}"
        self.log(user["name"], server.name, f"{post.id}: {what}", servers=[server.name])
        self.broadcast(server, post)

    def broadcast(self, server, post):
        mode = self.settings.delivery
        if mode == "total":
            server.waiting.append(post)
            if server.name == SEQUENCER:
                self.sequence(server, post)
            else:
                self.send(server, self.servers[SEQUENCER], self.sequence, post, f"{post.id}, to be numbered")
            return

        if mode == "fifo":
            post.seq = server.send_seq
        elif mode == "causal":
            post.deps = list(server.delivered)
            post.deps[server.index] = server.send_seq
        server.send_seq += 1

        for other in self.servers.values():
            if other is not server:
                self.send(server, other, self.receive, post, self.describe(post))
        self.receive(server, post)          # a server receives its own message straight away

    def sequence(self, sequencer, post):
        """Total order: the sequencer numbers each message and broadcasts it to everyone."""
        post.number = sequencer.next_to_give
        sequencer.next_to_give += 1
        self.log(sequencer.name, "", f"gives {post.id} number {post.number}", "event", [sequencer.name])
        for other in self.servers.values():
            if other is not sequencer:
                self.send(sequencer, other, self.receive, post, self.describe(post))
        self.receive(sequencer, post)

    # ---------- receiving and delivering ----------

    def ready(self, server, post):
        """Can this server deliver this message now?"""
        mode = self.settings.delivery
        if mode == "fifo":
            return post.seq == server.delivered[SERVERS.index(post.origin)]
        if mode == "causal":
            return all(d <= n for d, n in zip(post.deps, server.delivered))
        if mode == "total":
            return post.number == server.next_number
        return True

    def missing(self, server, post):
        """Why a message is not ready yet, in words."""
        mode = self.settings.delivery
        if mode == "fifo":
            return f"waiting for {post.origin}'s message {server.delivered[SERVERS.index(post.origin)] + 1}"
        if mode == "causal":
            gaps = [f"{name}'s message {n + 1}" for name, d, n in zip(SERVERS, post.deps, server.delivered) if d > n]
            return "waiting for " + " and ".join(gaps)
        return f"waiting for number {server.next_number}"

    def receive(self, server, post):
        server.buffer.append(post)
        if not self.ready(server, post):
            self.log(server.name, "", f"receives {self.describe(post)} and holds it in the buffer: "
                                      f"{self.missing(server, post)}", "held", [server.name])
            return
        first = True
        candidate = self.next_ready(server)
        while candidate is not None:
            server.buffer.remove(candidate)
            self.deliver(server, candidate, received_now=first and candidate is post)
            first = False
            candidate = self.next_ready(server)

    def next_ready(self, server):
        return next((p for p in server.buffer if self.ready(server, p)), None)

    def deliver(self, server, post, received_now):
        server.log.append(post)
        server.delivered[SERVERS.index(post.origin)] += 1
        if self.settings.delivery == "total":
            server.next_number += 1
            if post in server.waiting:
                server.waiting.remove(post)
        result = f": the topic is now {post.text}" if post.kind == "topic" else ""
        if post.kind == "topic":
            server.topic = post.text
        if post.origin == server.name and received_now and self.settings.delivery != "total":
            text = f"delivers {post.id}{result}"
        elif received_now:
            text = f"receives {self.describe(post)} and delivers it{result}"
        else:
            text = f"delivers {self.describe(post)} from the buffer{result}"
        self.log(server.name, "", text, "event", [server.name])

    # ---------- what the page shows ----------

    def state(self):
        mode = self.settings.delivery
        servers = []
        for server in self.servers.values():
            servers.append({
                "name": server.name,
                "crashed": server.crashed,
                "sequencer": mode == "total" and server.name == SEQUENCER,
                "delivered": server.delivered,
                "next_number": server.next_number,
                "next_to_give": server.next_to_give,
                "buffer": [self.describe(p) for p in server.buffer],
                "order": [p.id for p in server.log],
                "chat": [{"id": p.id, "author": p.author, "kind": p.kind, "text": p.text} for p in server.log],
                "waiting": [{"id": p.id, "author": p.author, "kind": p.kind, "text": p.text} for p in server.waiting],
                "topic": server.topic,
            })
        return {
            "now": self.now,
            "settings": asdict(self.settings),
            "servers": servers,
            "timeline": self.timeline,
        }


def replay(chat, recording):
    """Run a recorded afternoon of posts with the chat's current settings."""
    chat.settings.failure = recording.get("failure", "none")
    chat.lost = recording.get("lost", [1])
    chat.reset()
    users = {u["name"]: u for u in recording["users"]}
    for p in recording["posts"]:
        chat.schedule(p["time"], chat.post, users[p["user"]], p.get("kind", "chat"), p["text"])
    chat.run_until(recording["end"])
