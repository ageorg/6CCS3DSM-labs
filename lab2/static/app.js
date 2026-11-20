const STEPS = [
  { title: "Explore",
    text: "Book seats for Maya (London) and Leo (Dublin), and follow each booking through both data centres and the timeline. Nothing goes wrong yet." },
  { title: "Things go wrong",
    text: "Choose one thing that goes wrong; it happens at 0.500 s. Then try to book the same seat for Maya and for Leo, using Wait to let time pass. Before each action, write down what you expect to happen." },
  { title: "Fix it",
    text: "Change how Dublin behaves and try each failure again. Is there a setting that works well for all three?" },
];

let state = null;
let shown = null;   // null means everyone

function currentStep() {
  const match = location.hash.match(/step-(\d)/);
  return match ? Math.min(Math.max(Number(match[1]), 1), STEPS.length) : 1;
}

async function call(path, data) {
  const options = data === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
  const response = await fetch(path, options);
  state = await response.json();
  render();
}

function seconds(ms) {
  return (ms / 1000).toFixed(3) + " s";
}

function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}

function fillList(list, items, emptyText) {
  list.innerHTML = "";
  items.forEach(text => list.appendChild(element("li", text)));
  if (items.length === 0) list.appendChild(element("li", emptyText, "hint"));
}

function whoClass(name) {
  if (["London", "Dublin", "Network"].includes(name)) return "who " + name.toLowerCase();
  return name ? "who customer" : "";
}

function siteOf(name) {
  return state.sites.find(s => s.name === name);
}

function renderCustomers() {
  const box = document.getElementById("customers");
  box.innerHTML = "";
  const lab = state.mode === "lab";

  for (const customer of state.customers) {
    const site = siteOf(customer.site);
    const card = element("div", undefined, "card");
    card.appendChild(element("h3", customer.name));
    card.appendChild(element("p", `Books through ${customer.site}`, "hint"));

    if (lab) {
      card.appendChild(element("h4", `Seats, as ${customer.site} shows them`));
      const seats = element("div", undefined, "seats");
      for (const seat of state.seat_names) {
        const taken = seat in site.seats;
        const button = element("button", `${seat} ${taken ? "taken" : "free"}`, "seat " + (taken ? "taken" : "free"));
        button.disabled = taken;
        button.title = taken ? "" : `Book ${seat} for ${customer.name}`;
        button.onclick = () => call("/api/book", { customer: customer.name, seat });
        seats.appendChild(button);
      }
      card.appendChild(seats);
    }

    card.appendChild(element("h4", "Messages from the site"));
    const messages = element("ul");
    fillList(messages, state.messages.filter(m => m.customer === customer.name)
      .map(m => `${seconds(m.time)}: ${m.text}`), "none yet");
    card.appendChild(messages);

    card.appendChild(element("h4", `${customer.name}'s tickets`));
    const tickets = element("ul");
    fillList(tickets, state.tickets.filter(t => t.customer === customer.name)
      .map(t => `seat ${t.seat} (confirmed at ${seconds(t.time)})`), "none");
    card.appendChild(tickets);

    box.appendChild(card);
  }
}

function renderSite(site) {
  const box = document.getElementById("site-" + site.name);
  box.innerHTML = "";
  const title = element("h3", site.name);
  title.appendChild(element("span", site.role, "badge " + site.role));
  if (site.state !== "up") title.appendChild(element("span", site.state, "badge down"));
  box.appendChild(title);

  if (site.name === "Dublin") {
    box.appendChild(element("p", `Last heartbeat from London: ${seconds(site.last_heartbeat)}`));
    box.appendChild(element("p", site.role === "primary"
      ? "Has taken over from London."
      : `Thinks London has failed: ${site.suspects ? "yes" : "no"}`));
  } else {
    box.appendChild(element("p", "Sends Dublin a heartbeat every second and a copy of every booking."));
  }

  box.appendChild(element("h4", "Seat map, as this data centre sees it"));
  const seats = element("div", undefined, "seats");
  for (const seat of state.seat_names) {
    const holder = site.seats[seat];
    seats.appendChild(element("div", holder ? `${seat}: ${holder}` : `${seat}: free`, "seat" + (holder ? " taken" : "")));
  }
  box.appendChild(seats);
}

function renderSystem() {
  state.sites.forEach(renderSite);
  const link = document.getElementById("link");
  link.className = "link" + (state.link_up ? "" : " broken");
  link.textContent = state.link_up ? "◀ link working ▶" : "✕ link broken ✕";
}

function renderTimeline() {
  const picker = document.getElementById("picker");
  picker.innerHTML = "";
  for (const name of [null, ...state.customers.map(c => c.name)]) {
    const button = element("button", name || "Everyone", name === shown ? "chosen" : "");
    button.onclick = () => { shown = name; render(); };
    picker.appendChild(button);
  }

  const body = document.getElementById("timeline");
  body.innerHTML = "";
  const events = state.timeline.filter(e => shown === null || e.from === shown || e.to === shown
    || e.text.includes(shown) || (e.from === "Network" && !e.text.startsWith("lost:")) || e.text.startsWith("no heartbeat")
    || e.kind === "warn" || e.text.startsWith("London stops") || e.text.startsWith("London crashes")
    || e.text.startsWith("London carries") || e.text.startsWith("takes over") || e.text.startsWith("refuses bookings until")
    || e.text.startsWith("hears London"));
  for (const e of events) {
    const tr = element("tr", undefined, e.kind);
    tr.appendChild(element("td", seconds(e.time)));
    const from = element("td");
    from.appendChild(element("span", e.from, whoClass(e.from)));
    const to = element("td");
    if (e.to) to.appendChild(element("span", e.to, whoClass(e.to)));
    tr.append(from, to, element("td", e.text));
    body.appendChild(tr);
  }
  if (events.length === 0) {
    const tr = element("tr");
    const td = element("td", "nothing yet", "hint");
    td.colSpan = 4;
    tr.appendChild(td);
    body.appendChild(tr);
  }
}

function renderSettings() {
  const s = state.settings;
  for (const input of document.querySelectorAll("fieldset input")) {
    input.checked = String(s[input.name]) === input.value;
  }
  const f = state.fixed;
  const failureText = state.mode === "lab"
    ? `The chosen failure happens at ${seconds(f.failure_at)}; when London stops responding, it does so for ${f.pause / 1000} s. `
    : "";
  document.getElementById("fixed").textContent =
    `London sends Dublin a heartbeat every ${f.heartbeat / 1000} s. ${failureText}` +
    `Customers wait up to ${f.answer_wait / 1000} s for an answer, and Dublin waits up to ${f.forward_wait / 1000} s ` +
    `for London. Changing a setting starts again.`;
  document.getElementById("now").textContent = seconds(state.now);
}

function renderSteps(step) {
  const buttons = document.getElementById("step-buttons");
  buttons.innerHTML = "";
  STEPS.forEach((s, i) => {
    const button = element("button", `${i + 1}. ${s.title}`, i + 1 === step ? "chosen" : "");
    button.onclick = () => { location.hash = "step-" + (i + 1); };
    buttons.appendChild(button);
  });
  document.getElementById("step-text").textContent = STEPS[step - 1].text;
}

function render() {
  const lab = state.mode === "lab";
  const step = lab ? currentStep() : STEPS.length;

  document.getElementById("mode-note").textContent = lab
    ? "Work through the steps below in order."
    : "Replay: the network and the data centres behave as they did during the ticket release.";

  document.getElementById("steps").hidden = !lab;
  document.getElementById("recording").hidden = lab;
  if (lab) {
    renderSteps(step);
  } else {
    document.getElementById("recording-title").textContent = state.recording.title;
    document.getElementById("recording-description").textContent = state.recording.description;
    fillList(document.getElementById("complaints"),
      state.recording.complaints.map(c => `${c.customer}: “${c.text}”`), "");
  }

  document.getElementById("clock").hidden = !lab;
  document.getElementById("failures").hidden = !lab || step < 2;
  document.getElementById("behaviour").hidden = step < 3;
  document.getElementById("fixed").hidden = step < 2;
  document.getElementById("reset").hidden = !lab;

  renderCustomers();
  renderSystem();
  renderSettings();
  renderTimeline();
}

for (const input of document.querySelectorAll("fieldset input")) {
  input.addEventListener("change", () => {
    let value = input.value;
    if (input.name === "take_over") value = value === "true";
    if (input.name === "timeout") value = Number(value);
    call("/api/settings", { [input.name]: value });
  });
}
for (const button of document.querySelectorAll("[data-wait]")) {
  button.onclick = () => call("/api/wait", { ms: Number(button.dataset.wait) });
}
document.getElementById("reset").onclick = () => call("/api/reset", {});
document.getElementById("replay").onclick = () => call("/api/replay", {});
window.addEventListener("hashchange", render);

call("/api/state");
