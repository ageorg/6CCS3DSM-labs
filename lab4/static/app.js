const STEPS = [
  { title: "Explore",
    text: "Post messages and change the topic as Ana (London), Ben (Paris) and Chloe (Singapore). Follow each message to the three servers and through the timeline. Nothing goes wrong yet." },
  { title: "Things go wrong",
    text: "Choose what goes wrong, then follow the lab sheet. Before each case, write down what you expect each person's chat to show." },
  { title: "Fix it",
    text: "Change when the servers deliver messages and repeat what you did in step 2. Which setting handles every case?" },
];

const SERVERS = ["London", "Paris", "Singapore"];

let state = null;
let shown = null;   // null means every server

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
  if (SERVERS.includes(name)) return "who " + name.toLowerCase();
  if (name === "Network") return "who network";
  return name ? "who customer" : "";
}

function serverOf(name) {
  return state.servers.find(s => s.name === name);
}

function post(user, kind, text) {
  call("/api/post", { user, kind, text });
}

function chatLine(p, waiting) {
  const li = element("li", undefined, waiting ? "waiting" : "");
  li.appendChild(element("span", p.id, "id"));
  if (p.kind === "topic") {
    li.appendChild(element("span", `${p.author} set the topic to ${p.text}`, "topic-change"));
  } else {
    li.appendChild(element("strong", p.author + ": "));
    li.appendChild(document.createTextNode(p.text));
  }
  if (waiting) li.appendChild(element("span", " (sending…)", "hint"));
  return li;
}

function renderUsers() {
  const box = document.getElementById("users");
  box.innerHTML = "";
  const lab = state.mode === "lab";
  for (const name of SERVERS) {
    const users = state.users.filter(u => u.server === name);
    if (users.length === 0) continue;
    const server = serverOf(name);
    const card = element("div", undefined, "card");
    card.appendChild(element("h3", users.map(u => u.name).join(" and ")));
    card.appendChild(element("p", `Works through ${name}`, "hint"));
    if (server.crashed) card.appendChild(element("p", `${name} is not responding`, "down-note"));

    card.appendChild(element("div", `Topic: ${server.topic}`, "topic"));
    const chat = element("ul", undefined, "chat");
    server.chat.forEach(p => chat.appendChild(chatLine(p, false)));
    server.waiting.forEach(p => chat.appendChild(chatLine(p, true)));
    if (server.chat.length === 0 && server.waiting.length === 0) chat.appendChild(element("li", "no messages yet", "hint"));
    card.appendChild(chat);

    if (lab) {
      for (const user of users) {
        const says = element("div", undefined, "options");
        says.appendChild(element("span", "Post: ", "label"));
        for (const text of user.says) {
          const button = element("button", text, "small");
          button.disabled = server.crashed;
          button.onclick = () => post(user.name, "chat", text);
          says.appendChild(button);
        }
        card.appendChild(says);
        const topics = element("div", undefined, "options");
        topics.appendChild(element("span", "Set the topic: ", "label"));
        for (const text of state.topics) {
          const button = element("button", text, "small");
          button.disabled = server.crashed;
          button.onclick = () => post(user.name, "topic", text);
          topics.appendChild(button);
        }
        card.appendChild(topics);
      }
    }
    box.appendChild(card);
  }
}

function renderServer(server) {
  const box = document.getElementById("server-" + server.name);
  box.innerHTML = "";
  const title = element("h3", server.name);
  if (server.sequencer) title.appendChild(element("span", "sequencer", "badge"));
  if (server.crashed) title.appendChild(element("span", "crashed", "badge down"));
  box.appendChild(title);

  const mode = state.settings.delivery;
  if (mode === "fifo" || mode === "causal") {
    box.appendChild(element("p", `delivered = ⟨${server.delivered.join(", ")}⟩`, "counter"));
    box.appendChild(element("p", "messages delivered from London, Paris and Singapore", "hint small"));
  }
  if (mode === "total") {
    box.appendChild(element("p", `Next number to deliver: ${server.next_number}`, "counter"));
    if (server.sequencer) box.appendChild(element("p", `Next number to give out: ${server.next_to_give}`, "counter"));
  }

  box.appendChild(element("h4", "Buffer: received, not yet delivered"));
  const buffer = element("ul");
  fillList(buffer, server.buffer, "empty");
  box.appendChild(buffer);

  box.appendChild(element("h4", "Delivered, in this order"));
  box.appendChild(element("p", server.order.length ? server.order.join(", ") : "nothing yet",
    server.order.length ? "order" : "hint"));
}

function renderTimeline() {
  const picker = document.getElementById("picker");
  picker.innerHTML = "";
  for (const name of [null, ...SERVERS]) {
    const button = element("button", name || "Everything", name === shown ? "chosen" : "");
    button.onclick = () => { shown = name; render(); };
    picker.appendChild(button);
  }

  const body = document.getElementById("timeline");
  body.innerHTML = "";
  const events = state.timeline.filter(e => shown === null || e.servers.includes(shown));
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
  for (const input of document.querySelectorAll("fieldset input")) {
    input.checked = state.settings[input.name] === input.value;
  }
  const f = state.fixed;
  document.getElementById("fixed").textContent =
    `A message takes ${f.delay / 1000} s to go from one server to another. A lost message is sent again ` +
    `${f.resend / 1000} s later. Changing a setting starts again.`;
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
    : "Replay: the servers and the network behave as they did that afternoon.";

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

  renderUsers();
  state.servers.forEach(renderServer);
  renderSettings();
  renderTimeline();
}

for (const input of document.querySelectorAll("fieldset input")) {
  input.addEventListener("change", () => call("/api/settings", { [input.name]: input.value }));
}
for (const button of document.querySelectorAll("[data-wait]")) {
  button.onclick = () => call("/api/wait", { ms: Number(button.dataset.wait) });
}
document.getElementById("reset").onclick = () => call("/api/reset", {});
document.getElementById("replay").onclick = () => call("/api/replay", {});
window.addEventListener("hashchange", render);

call("/api/state");
