const STEPS = [
  { title: "Explore",
    text: "Use the shop as a customer: add items, pay, and follow each order through the system and the timeline. Nothing goes wrong yet." },
  { title: "Things go wrong",
    text: "Choose one thing that goes wrong, then pay. Before you press Pay, write down what you expect the customer, the shop and Payment to see." },
  { title: "Fix it",
    text: "Keep the failure chosen, change how the shop behaves, and pay again. Does the problem go away?" },
];

let state = null;
let selectedOrder = null;   // null means all orders
let baskets = null;         // customer name -> list of item names

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
  if (baskets === null) fillBaskets();
  render();
}

function fillBaskets() {
  baskets = {};
  state.customers.forEach(c => { baskets[c.name] = [...c.basket]; });
}

function seconds(ms) {
  return (ms / 1000).toFixed(3) + " s";
}

function money(amount) {
  return "£" + amount.toFixed(2);
}

function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}

function fillList(listId, items, emptyText) {
  const list = document.getElementById(listId);
  list.innerHTML = "";
  items.forEach(text => list.appendChild(element("li", text)));
  if (items.length === 0) list.appendChild(element("li", emptyText, "hint"));
}

function fillRow(row, values, tag) {
  row.innerHTML = "";
  values.forEach(value => row.appendChild(element(tag, value)));
}

function whoClass(name) {
  if (["Shop", "Stock", "Payment", "Network"].includes(name)) return "who " + name.toLowerCase();
  return name ? "who customer" : "";
}

async function pay(name) {
  await call("/api/pay", { customer: name, items: baskets[name] });
  const order = state.orders[state.orders.length - 1];
  if (order.status !== "failed") baskets[name] = [];   // a failed order keeps its basket
  selectedOrder = order.id;
  render();
}

function basketBox(customer) {
  const lab = state.mode === "lab";
  const items = lab ? baskets[customer.name] : customer.basket;
  const box = element("div", undefined, "basket");
  box.appendChild(element("h4", lab ? "Basket" : "Basket at checkout"));

  const list = element("ul");
  items.forEach((item, index) => {
    const li = element("li", `${item}, ${money(state.catalogue[item])} `);
    if (lab) {
      const remove = element("button", "remove", "small");
      remove.onclick = () => { baskets[customer.name].splice(index, 1); render(); };
      li.appendChild(remove);
    }
    list.appendChild(li);
  });
  if (items.length === 0) list.appendChild(element("li", "empty", "hint"));
  box.appendChild(list);

  const total = items.reduce((sum, item) => sum + state.catalogue[item], 0);
  box.appendChild(element("p", "Total: " + money(total), "total"));

  if (lab) {
    const button = element("button", "Pay " + money(total), "pay");
    button.disabled = items.length === 0;
    button.onclick = () => pay(customer.name);
    box.appendChild(button);
  }
  return box;
}

function productsBox(customer) {
  const box = element("div");
  box.appendChild(element("h4", "Products"));
  for (const [item, price] of Object.entries(state.catalogue)) {
    const button = element("button", `${item} ${money(price)}`, "small");
    button.title = "Add to basket";
    button.onclick = () => { baskets[customer.name].push(item); render(); };
    box.appendChild(button);
  }
  return box;
}

function renderCustomers() {
  const box = document.getElementById("customers");
  box.innerHTML = "";

  for (const customer of state.customers) {
    const card = element("div", undefined, "card");
    card.appendChild(element("h3", customer.name));
    if (state.mode === "lab") card.appendChild(productsBox(customer));
    card.appendChild(basketBox(customer));

    card.appendChild(element("h4", "Messages from the shop"));
    const messages = element("ul");
    state.timeline
      .filter(e => e.to === customer.name)
      .forEach(e => messages.appendChild(element("li", `${seconds(e.time)}: ${e.text}`)));
    if (!messages.children.length) messages.appendChild(element("li", "none yet", "hint"));
    card.appendChild(messages);

    card.appendChild(element("h4", `${customer.name}'s bank statement`));
    const bank = element("ul");
    state.charges
      .filter(c => c.customer === customer.name)
      .forEach(c => bank.appendChild(element("li", `${seconds(c.time)}: ${c.items}, ${money(c.amount)}`)));
    if (!bank.children.length) bank.appendChild(element("li", "no charges", "hint"));
    card.appendChild(bank);

    box.appendChild(card);
  }
}

function renderSystem() {
  fillList("reservations",
    state.reservations.map(r => `${seconds(r.time)}: ${r.items} for ${r.customer}`),
    "none yet");

  const showKeys = state.settings.use_key || state.orders.some(o => o.key);
  const head = ["Order", "Customer", "Items", "Total", "Status"].concat(showKeys ? ["Key"] : []);
  fillRow(document.getElementById("orders-head"), head, "th");
  const orders = document.getElementById("orders");
  orders.innerHTML = "";
  for (const o of state.orders) {
    const row = document.createElement("tr");
    const values = ["#" + o.id, o.customer, o.description, money(o.total), o.status];
    if (showKeys) values.push(o.key || "none");
    fillRow(row, values, "td");
    orders.appendChild(row);
  }

  const charges = document.getElementById("charges");
  charges.innerHTML = "";
  for (const c of state.charges) {
    const row = document.createElement("tr");
    fillRow(row, [seconds(c.time), c.customer, c.items, money(c.amount)], "td");
    charges.appendChild(row);
  }
}

function renderTimeline() {
  const picker = document.getElementById("order-picker");
  picker.innerHTML = "";
  const choices = [{ label: "All orders", id: null }]
    .concat(state.orders.map(o => ({ label: `Order #${o.id} (${o.customer})`, id: o.id })));
  for (const choice of choices) {
    const button = element("button", choice.label, choice.id === selectedOrder ? "chosen" : "");
    button.onclick = () => { selectedOrder = choice.id; render(); };
    picker.appendChild(button);
  }

  const body = document.getElementById("timeline");
  body.innerHTML = "";
  const events = state.timeline.filter(e => selectedOrder === null || e.order === selectedOrder);
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
    const value = state.settings[input.name];
    if (input.type === "radio") input.checked = input.value === value;
    else input.checked = value;
  }
  document.getElementById("fixed").textContent =
    `The shop waits ${state.timeout / 1000} s for a reply from Payment and makes up to ` +
    `${state.max_attempts} attempts, 0.5 s apart.`;
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
    : "Replay: the network and the services behave as they did that evening.";

  document.getElementById("steps").hidden = !lab;
  document.getElementById("recording").hidden = lab;
  if (!lab) {
    document.getElementById("recording-title").textContent = state.recording.title;
    document.getElementById("recording-description").textContent = state.recording.description;
    fillList("complaints", state.recording.complaints.map(c => `${c.customer}: “${c.text}”`), "");
  } else {
    renderSteps(step);
  }

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
    const value = input.type === "radio" ? input.value : input.checked;
    call("/api/settings", { [input.name]: value });
  });
}

document.getElementById("reset").onclick = () => {
  selectedOrder = null;
  baskets = null;
  call("/api/reset", {});
};
document.getElementById("replay").onclick = () => { selectedOrder = null; call("/api/replay", {}); };
window.addEventListener("hashchange", render);

call("/api/state");
