const STEPS = [
  { title: "Explore",
    text: "Change the time or the place as Ana (London) and as Ben (New York), and follow each edit to both servers and through the timeline. Nothing goes wrong yet." },
  { title: "Things go wrong",
    text: "Choose what goes wrong, then follow the lab sheet. Before each change, write down what you expect both pages to show afterwards." },
  { title: "Fix it",
    text: "Change how the servers stamp each edit and repeat what you did in step 2. Which setting handles every case correctly?" },
];

const FIELD_NAMES = { time: "Time", place: "Place" };

let state = null;
let shown = null;   // null means every field

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
  if (name === "London") return "who london";
  if (name === "New York") return "who newyork";
  if (name === "Network") return "who network";
  return name ? "who customer" : "";
}

function serverOf(name) {
  return state.servers.find(s => s.name === name);
}

function edit(user, field, value) {
  call("/api/edit", { user, field, value });
}

function fieldBox(user, server, field) {
  const versions = server.fields[field];
  const box = element("div", undefined, "field");
  const lab = state.mode === "lab";

  if (versions.length === 1) {
    const line = element("div", `${FIELD_NAMES[field]}: `);
    line.appendChild(element("span", versions[0].value, "value"));
    box.appendChild(line);
    if (lab) {
      const options = element("div", undefined, "options");
      for (const value of state.field_options[field]) {
        if (value === versions[0].value) continue;
        const button = element("button", `Change to ${value}`, "small");
        button.onclick = () => edit(user.name, field, value);
        options.appendChild(button);
      }
      box.appendChild(options);
    }
  } else {
    box.appendChild(element("div", `${FIELD_NAMES[field]}: two versions, ` +
      versions.map(v => `${v.value} (${v.author})`).join(" or "), "conflict"));
    if (lab) {
      const options = element("div", undefined, "options");
      for (const v of versions) {
        const button = element("button", `Keep ${v.value}`, "small");
        button.onclick = () => edit(user.name, field, v.value);
        options.appendChild(button);
      }
      box.appendChild(options);
    }
  }
  return box;
}

function renderUsers() {
  const box = document.getElementById("users");
  box.innerHTML = "";
  for (const user of state.users) {
    const server = serverOf(user.server);
    const card = element("div", undefined, "card");
    card.appendChild(element("h3", user.name));
    card.appendChild(element("p", `Works through ${user.server}`, "hint"));
    card.appendChild(element("h4", `The away day, as ${user.server} shows it`));
    for (const field of Object.keys(FIELD_NAMES)) card.appendChild(fieldBox(user, server, field));

    card.appendChild(element("h4", `${user.name}'s changes`));
    const changes = element("ul");
    fillList(changes, state.timeline.filter(e => e.from === user.name)
      .map(e => `${seconds(e.time)}: ${e.text}`), "none yet");
    card.appendChild(changes);
    box.appendChild(card);
  }
}

function renderServer(server) {
  const box = document.getElementById("server-" + server.name);
  box.innerHTML = "";
  box.appendChild(element("h3", server.name));
  box.appendChild(element("p", `Its clock reads ${server.clock}`, "clockline"));
  const stamps = state.settings.stamps;
  if (stamps === "lamport") box.appendChild(element("p", `Lamport clock: ${server.lamport}`, "clockline"));
  if (stamps === "vector") box.appendChild(element("p", `Vector clock: ⟨${server.vector[0]}, ${server.vector[1]}⟩`, "clockline"));

  box.appendChild(element("h4", "Its copy of the page"));
  for (const field of Object.keys(FIELD_NAMES)) {
    const versions = server.fields[field];
    const line = element("div", `${FIELD_NAMES[field]}: `, "field");
    versions.forEach((v, i) => {
      if (i > 0) line.appendChild(document.createTextNode(" and "));
      line.appendChild(element("span", v.value, "value"));
      line.appendChild(element("span", `${v.author}, ${v.stamp}`, "stamp"));
    });
    if (versions.length > 1) line.appendChild(element("span", " (conflict)", "conflict"));
    box.appendChild(line);
  }
}

function renderTimeline() {
  const picker = document.getElementById("picker");
  picker.innerHTML = "";
  for (const field of [null, ...Object.keys(FIELD_NAMES)]) {
    const button = element("button", field ? FIELD_NAMES[field] : "Everything", field === shown ? "chosen" : "");
    button.onclick = () => { shown = field; render(); };
    picker.appendChild(button);
  }

  const body = document.getElementById("timeline");
  body.innerHTML = "";
  const events = state.timeline.filter(e => shown === null || e.field === shown);
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
  document.getElementById("delay").textContent = `take ${state.fixed.sync_delay / 1000} s`;
  document.getElementById("fixed").textContent =
    `An update takes ${state.fixed.sync_delay / 1000} s to reach the other server. When two versions of a field ` +
    `meet, a server keeps the later one, judged by their timestamps. Changing a setting starts again.`;
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
    : "Replay: the servers and their clocks behave as they did that afternoon.";

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
