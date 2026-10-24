/* StormDesk console: the screen the human technician works from.

   Everything comes from the /admin endpoints; the open tab refreshes itself every few seconds, so a
   request made on a live call shows up while the caller is still on the line. Every value from the
   server goes through html`` (which escapes it) or textContent, never straight into innerHTML. */
"use strict";

(() => {
  // --- safe HTML ----------------------------------------------------------------------------------

  class Safe { constructor(markup) { this.markup = markup; } }
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" };
  const esc = (text) => String(text).replace(/[&<>"'`]/g, (c) => ESC[c]);
  const part = (v) => (v == null || v === false ? "" : v instanceof Safe ? v.markup
    : Array.isArray(v) ? v.map(part).join("") : esc(v));
  const html = (strings, ...values) => new Safe(strings.reduce((out, s, i) => out + part(values[i - 1]) + s));
  const trusted = (markup) => new Safe(markup); // only ever for constants written in this file

  const ICONS = {
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    storm: '<path d="M6 16.326A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.973"/><path d="m13 12-3 5h4l-3 5"/>',
    ticket: '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/>',
    phone: '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
    headset: '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
    review: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    flask: '<path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    play: '<polygon points="6 3 20 12 6 21 6 3"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    bolt: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    bulb: '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    minus: '<path d="M5 12h14"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  };
  const icon = (name) => trusted(`<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`);

  // --- labels -------------------------------------------------------------------------------------

  const TABS = [
    { id: "approvals", label: "Approvals", icon: "bell", every: 3000 },
    { id: "storm", label: "Storm board", icon: "storm", every: 5000 },
    { id: "tickets", label: "Tickets", icon: "ticket", every: 10000 },
    { id: "phones", label: "Phones", icon: "phone", every: 3000 },
    { id: "calls", label: "Calls", icon: "headset", every: 8000 },
    { id: "reviews", label: "Reviews", icon: "review", every: 8000 },
    { id: "drills", label: "Drills", icon: "flask", every: 5000 },
  ];
  const KIND = { mfa_reset: "MFA reset", account_unlock: "Account unlock", access_grant: "Access grant",
    major_incident: "Major incident" };
  const DRILL = { itsm_down: "Ticket system down", sms_down: "Text messages down",
    identity_down: "Identity system down", feeds_down: "Status pages unreachable" };
  const RISK_TONE = { low: "ok", medium: "warn", high: "bad" };
  const STATUS_TONE = { pending: "warn", approved: "info", executed: "ok", rejected: "bad", failed: "bad" };
  const STATE_TONE = { new: "info", in_progress: "info", on_hold: "warn", resolved: "ok" };
  const VERDICT = { pass: { tone: "ok", icon: "check", label: "Pass" },
    attention: { tone: "warn", icon: "alert", label: "Attention" }, fail: { tone: "bad", icon: "x", label: "Fail" } };
  const RESULT = { pass: ["ok", "check"], fail: ["bad", "x"], warn: ["warn", "alert"] };
  const TOAST_ICON = { ok: "check", bad: "alert", warn: "bell", info: "info" };
  const LIVE_STATES = ["operational", "degraded", "outage"];
  const LOCATIONS = ["Chennai", "Bengaluru", "London", "Austin", "Remote"];
  const CODE = /code is (\d{6})/;
  const STATUS_EVERY = 20000;
  const OFFLINE = "Can't reach StormDesk. Is the backend still running? Start it with: "
    + "uv run uvicorn stormdesk.main:app --port 8000";

  // --- state --------------------------------------------------------------------------------------

  const state = {
    tab: "approvals",
    technician: "",
    employees: {},
    services: [],
    selected: { tickets: null, calls: null, reviews: null },
    tickets: [],
    ticketDetail: null,
    status: null,
    seenPending: 0,
  };
  // What the technician has typed or picked, kept across the automatic refreshes.
  const drafts = { demo_title: "Users unable to connect", demo_impact: "outage", storm_service: "vpn",
    storm_location: "Chennai", storm_count: "2", reset_confirm: false };
  const openSteps = new Set();

  const $ = (selector, root = document) => root.querySelector(selector);
  const region = (name) => $(`[data-region="${name}"]`);
  const enc = encodeURIComponent;
  const words = (s) => String(s ?? "").replaceAll("_", " ");
  const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
  const clip = (s, n) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s || "");

  function stored(area, key) {
    try { return window[area].getItem(key); } catch { return null; }
  }
  function keep(area, key, value) {
    try { if (value) window[area].setItem(key, value); else window[area].removeItem(key); } catch { /* private mode */ }
  }

  // --- talking to the backend ---------------------------------------------------------------------

  let adminKey = stored("sessionStorage", "stormdesk-admin-key") || "";

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  function detailOf(data) {
    const detail = data && data.detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    return detail ? String(detail) : "";
  }

  async function api(path, { method = "GET", body, params } = {}) {
    const url = new URL(path, location.origin);
    Object.entries(params || {}).forEach(([k, v]) => { if (v != null && v !== "") url.searchParams.set(k, v); });
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (adminKey) headers["X-StormDesk-Admin-Key"] = adminKey;
    let resp;
    try {
      resp = await fetch(url, { method, headers, cache: "no-store",
        body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      online(false);
      throw new ApiError(0, OFFLINE);
    }
    online(true);
    const data = await resp.json().catch(() => null);
    if (resp.status === 401) askForKey();
    if (!resp.ok) throw new ApiError(resp.status, detailOf(data) || `${resp.status} ${resp.statusText}`);
    return data;
  }

  const missing = (err) => (err.status === 404 ? null : Promise.reject(err));

  // --- painting -----------------------------------------------------------------------------------

  const painted = new WeakMap();

  /* Replace a region only when its content really changed, keeping focus, typing and scroll. */
  function paint(el, content) {
    const markup = part(content);
    if (painted.get(el) === markup) return;
    const active = document.activeElement;
    const focusKey = active && el.contains(active) ? active.dataset.draft : null;
    const caret = focusKey && typeof active.selectionStart === "number" ? [active.selectionStart, active.selectionEnd] : null;
    const scrolls = [...el.querySelectorAll("[data-scroll]")].map((s) => [s.dataset.scroll, s.scrollTop]);
    el.innerHTML = markup;
    painted.set(el, markup);
    hydrate(el);
    for (const [key, top] of scrolls) {
      const scroller = $(`[data-scroll="${CSS.escape(key)}"]`, el);
      if (scroller) scroller.scrollTop = top;
    }
    if (focusKey) {
      const again = $(`[data-draft="${CSS.escape(focusKey)}"]`, el);
      if (again) {
        again.focus({ preventScroll: true });
        if (caret) try { again.setSelectionRange(...caret); } catch { /* not a text box */ }
      }
    }
  }

  function hydrate(root) {
    for (const input of root.querySelectorAll("[data-draft]")) {
      const key = input.dataset.draft;
      if (!(key in drafts)) continue;
      if (input.type === "checkbox") input.checked = Boolean(drafts[key]);
      else if (input.type === "radio") input.checked = drafts[key] === input.value;
      else input.value = drafts[key];
    }
    for (const step of root.querySelectorAll("details[data-key]")) step.open = openSteps.has(step.dataset.key);
    for (const bar of root.querySelectorAll("[data-width]")) bar.style.width = `${bar.dataset.width}%`;
    fillTimes(root);
  }

  function ago(ts) {
    const minutes = Math.floor((Date.now() - Date.parse(ts)) / 60000);
    if (!(minutes >= 1)) return "just now";
    if (minutes < 60) return `${plural(minutes, "minute")} ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${plural(hours, "hour")} ago`;
    const days = Math.floor(hours / 24);
    return days === 1 ? "yesterday" : `${days} days ago`;
  }

  function fillTimes(root = document) {
    for (const t of root.querySelectorAll("time[data-ts]")) {
      t.textContent = ago(t.dataset.ts);
      t.title = new Date(t.dataset.ts).toLocaleString();
      t.dateTime = t.dataset.ts;
    }
  }

  // Relative times are filled in after painting, so "2 minutes ago" ticking over never forces a repaint.
  const when = (ts) => (ts ? html`<time data-ts="${ts}"></time>` : "—");
  const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

  function who(id) {
    const person = state.employees[id || ""];
    return person ? `${person.full_name} (${id})` : id || "—";
  }
  // In tables: the name, with the employee ID underneath, so names don't wrap.
  function person(id) {
    const found = state.employees[id || ""];
    return found ? html`<span class="who">${found.full_name}<small>${id}</small></span>` : id || "—";
  }
  const serviceName = (key) => (state.services.find((s) => s.key === key) || {}).name || key || "";

  // --- building blocks ----------------------------------------------------------------------------

  const chip = (text, tone = "", ic = null) => html`<span class="chip ${tone}">${ic ? icon(ic) : ""}${text}</span>`;
  const empty = (text, ic = "inbox", tone = "") => html`<div class="empty ${tone}">${icon(ic)}<span>${text}</span></div>`;
  const hint = (text) => html`<div class="hint-pane">${text}</div>`;
  const pretty = (value) => JSON.stringify(value ?? {}, null, 2);
  const omit = (obj, key) => Object.fromEntries(Object.entries(obj || {}).filter(([k]) => k !== key));

  function card({ title, ic, aside, tone = "", body, cls = "", foot }) {
    return html`<article class="card ${cls}">
      <header class="card-head ${tone}">${ic ? icon(ic) : ""}<h3>${title}</h3>${aside ? html`<div class="card-aside">${aside}</div>` : ""}</header>
      <div class="card-body">${body}</div>${foot ? html`<footer class="card-foot">${foot}</footer>` : ""}
    </article>`;
  }

  /* pick: { kind, id(row), current } makes rows clickable; scroll names a scroller kept across refreshes. */
  function table(columns, rows, { pick, scroll, tall } = {}) {
    const body = rows.map((row) => {
      const id = pick ? pick.id(row) : null;
      const attrs = pick ? html` class="pick" data-action="pick" data-kind="${pick.kind}" data-id="${id}" tabindex="0" aria-selected="${String(id === pick.current)}"` : "";
      return html`<tr${attrs}>${columns.map((c) => html`<td class="${c.cls || ""}">${c.cell(row)}</td>`)}</tr>`;
    });
    return html`<div class="table-wrap ${tall ? "tall" : ""}"${scroll ? html` data-scroll="${scroll}"` : ""}><table>
      <thead><tr>${columns.map((c) => html`<th>${c.label}</th>`)}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  // --- the bar at the top: numbers, alerts, tab badges --------------------------------------------

  async function loadOverview() {
    const o = await api("/admin/overview");
    $("#company").textContent = o.company;
    const reviewed = Object.values(o.reviews).reduce((a, b) => a + b, 0);
    const toLook = (o.reviews.attention || 0) + (o.reviews.fail || 0);
    const tiles = [
      { label: "Waiting for your approval", value: o.pending_approvals, ic: "bell", tab: "approvals",
        note: o.pending_approvals ? "A caller may be holding" : "All clear", cls: o.pending_approvals ? "hot" : "" },
      { label: "Open tickets", value: o.open_incidents, ic: "ticket", tab: "tickets", note: "Across every service" },
      { label: "Major incidents", value: o.major_incidents, ic: "bolt", tab: "storm",
        note: o.major_incidents ? "Being worked on" : "None declared", cls: o.major_incidents ? "alarm" : "" },
      { label: "Storms building", value: o.storms_building, ic: "storm", tab: "storm",
        note: o.storms_building ? "The next caller may tip it" : "It's quiet", cls: o.storms_building ? "hot" : "" },
      { label: "Reviews to look at", value: toLook, ic: "review", tab: "reviews", note: `${plural(reviewed, "call")} reviewed` },
    ];
    paint($("#kpis"), tiles.map((t) => html`<button class="kpi ${t.cls || ""}" type="button" data-action="goto" data-tab="${t.tab}">
      <span class="kpi-label">${icon(t.ic)}${t.label}</span><span class="kpi-value">${t.value}</span><span class="kpi-note">${t.note}</span></button>`));
    paint($("#alerts"), [
      ...o.drills_on.map((flag) => html`<button class="chip bad" type="button" data-action="goto" data-tab="drills">${icon("flask")}Drill on: ${DRILL[flag] || flag}</button>`),
      o.outbox_pending ? html`<button class="chip warn" type="button" data-action="goto" data-tab="drills">${icon("inbox")}${plural(o.outbox_pending, "ticket")} waiting in the outbox</button>` : "",
      ...o.demo_outages.map((key) => html`<button class="chip info" type="button" data-action="goto" data-tab="storm">${icon("play")}Demo outage: ${serviceName(key)}</button>`),
    ]);
    badge("approvals", o.pending_approvals);
    badge("reviews", toLook, "bad");
    document.title = o.pending_approvals ? `(${o.pending_approvals}) StormDesk Console` : "StormDesk Console";
    if (o.pending_approvals > state.seenPending) {
      toast(`${plural(o.pending_approvals, "approval")} waiting`, "warn", "bell");
    }
    state.seenPending = o.pending_approvals;
  }

  function badge(tab, count, tone = "") {
    const el = $(`[data-count="${tab}"]`);
    el.hidden = !count;
    el.textContent = count;
    el.className = `count ${tone}`;
  }

  async function loadEmployees() {
    const [{ employees }, { services }] = await Promise.all([api("/admin/employees"), api("/admin/services")]);
    state.employees = Object.fromEntries(employees.map((e) => [e.employee_id, e]));
    state.services = services;
    if (!drafts.demo_service && services.length) drafts.demo_service = services[0].key;

    const technicians = employees.filter((e) => e.department === "IT" && e.status === "active");
    const ids = technicians.map((t) => t.employee_id);
    const saved = stored("localStorage", "stormdesk-technician");
    state.technician = [saved, state.technician, "E1019"].find((id) => ids.includes(id)) || ids[0] || "";
    const options = (people) => people.map((p) => html`<option value="${p.employee_id}">${p.full_name} (${p.employee_id})</option>`);
    $("#technician").innerHTML = part(options(technicians));
    $("#technician").value = state.technician;

    const phone = $("#phone-of");
    const wanted = phone.value || stored("localStorage", "stormdesk-phone") || "E1001";
    phone.innerHTML = part(options(employees));
    phone.value = state.employees[wanted] ? wanted : (employees[0] || {}).employee_id || "";
  }

  // --- approvals ----------------------------------------------------------------------------------

  const DECIDED = [
    { label: "Approval", cell: (a) => html`<span class="mono">${a.approval_id}</span>`, cls: "nowrap" },
    { label: "What", cell: (a) => KIND[a.kind] || a.kind, cls: "nowrap" },
    { label: "For", cell: (a) => (a.employee_id ? person(a.employee_id) : serviceName(a.service)) },
    { label: "Status", cell: (a) => chip(a.status, STATUS_TONE[a.status]) },
    { label: "Decided by", cell: (a) => (a.decided_by ? person(a.decided_by) : "—") },
    { label: "When", cell: (a) => when(a.decided_at || a.completed_at), cls: "nowrap" },
  ];

  async function loadApprovals() {
    const [pending, recent] = await Promise.all([
      api("/admin/approvals", { params: { status: "pending" } }),
      api("/admin/approvals", { params: { limit: 30 } }),
    ]);
    // Oldest first: first come, first served (ids break ties within the same second).
    const queue = pending.approvals.slice().sort((a, b) => a.created_at.localeCompare(b.created_at)
      || a.approval_id.localeCompare(b.approval_id));
    const decided = recent.approvals.filter((a) => a.status !== "pending");
    paint(region("approvals"), html`
      ${queue.length ? html`<div class="grid cols-2">${queue.map(approvalCard)}</div>`
        : empty("Nothing waiting for approval.", "check", "ok")}
      ${decided.length ? html`<div class="section-label">Recently decided</div>
        ${card({ title: plural(decided.length, "decision"), ic: "history", cls: "flush", body: table(DECIDED, decided) })}` : ""}`);
  }

  function approvalCard(a) {
    const id = a.approval_id;
    const major = a.kind === "major_incident";
    const details = a.details || {};
    const ticket = a.incident_number || details.ticket_reference;
    const person = state.employees[a.employee_id || ""];
    const own = Boolean(a.employee_id) && a.employee_id === state.technician;
    const off = own ? trusted(" disabled") : "";
    const notes = a.risk_notes || [];
    return card({
      title: html`${KIND[a.kind] || a.kind} · ${major ? serviceName(a.service) : who(a.employee_id)}`,
      ic: major ? "storm" : "shield",
      aside: chip(`risk: ${a.risk_level}`, RISK_TONE[a.risk_level]),
      body: html`
        <p class="meta"><span class="mono">${id}</span> · requested ${when(a.created_at)}${ticket ? html` · ticket <span class="mono">${ticket}</span>` : ""}${person ? ` · ${person.department}, ${person.location}` : ""}</p>
        <dl class="kv"><dt>${major ? "Why" : "Caller says"}</dt><dd>${a.reason}</dd>
          ${details.resource ? html`<dt>Access to</dt><dd>${details.resource}</dd>` : ""}</dl>
        <div><span class="label">${major ? "Evidence" : "Risk signals"}</span>
          ${notes.length ? html`<ul class="bullets">${notes.map((n) => html`<li>${n}</li>`)}</ul>` : html`<p class="meta">None.</p>`}</div>
        <input class="input" data-draft="note-${id}" placeholder="Note (internal; never read to the caller)" aria-label="Internal note for ${id}">
        <div class="pair">
          <button class="btn primary" type="button" data-action="decide" data-id="${id}" data-approve="1"${off}>${icon("check")}${major ? "Declare major incident" : "Approve"}</button>
          <button class="btn" type="button" data-action="decide" data-id="${id}" data-approve="0"${off}>${icon("x")}${major ? "Not a major incident" : "Reject"}</button>
        </div>
        ${own ? html`<p class="meta">This is your own request: another technician has to decide it.</p>` : ""}`,
    });
  }

  async function decide(id, approve) {
    const result = await api(`/admin/approvals/${enc(id)}/decision`, { method: "POST",
      body: { technician_id: state.technician, approve, note: drafts[`note-${id}`] || "" } });
    delete drafts[`note-${id}`];
    toast(`${id} ${approve ? "approved" : "rejected"}.`, approve ? "ok" : "info");
    if (result.status === "failed") toast(`${id} was approved but could not be applied: ${result.result || "unknown error"}`, "bad");
  }

  // --- storm board --------------------------------------------------------------------------------

  async function loadStorm() {
    const due = !state.status || Date.now() - state.status.at > STATUS_EVERY;
    const [board, live] = await Promise.all([api("/admin/storm-board"), due ? api("/status/overview") : null]);
    if (live) state.status = { at: Date.now(), services: live.services };
    paint(region("storm"), board.services.length ? html`<div class="grid cols-2">${board.services.map(stormCard)}</div>`
      : empty("No ticket storms. It's quiet.", "storm", "ok"));
    paintStatus();
  }

  function stormCard(row) {
    const major = row.major_incident;
    const places = Object.entries(row.locations || {}).map(([where, n]) => `${n} from ${where}`).join(", ");
    const reports = places ? html`<p class="meta">Reports: ${places}</p>` : "";
    if (major) {
      return card({
        title: html`${row.service} · major incident <span class="mono">${major.number}</span>`,
        ic: "bolt", tone: "bad", aside: chip(`${major.linked_open} linked open`, "bad"),
        body: html`<p><b>${major.summary}</b></p>
          <p class="meta">Declared ${major.opened} · ${plural(major.linked_open, "linked ticket")} still open</p>${reports}
          <input class="input" data-draft="resolve-${major.number}" placeholder="Resolution note, e.g. VPN gateway restarted" aria-label="Resolution note">
          <button class="btn primary block" type="button" data-action="resolve" data-number="${major.number}">${icon("check")}Resolve and text everyone affected</button>`,
      });
    }
    const pct = Math.min(100, Math.round((row.open_reports / row.threshold) * 100));
    return card({
      title: row.service, ic: "storm",
      aside: row.proposal ? chip("Proposal waiting", "warn") : chip("Building", "info"),
      body: html`<div class="meter-text"><span><b>${row.open_reports}</b> of ${row.threshold} reports</span><span>last ${row.window_minutes} minutes</span></div>
        <div class="meter ${pct >= 100 ? "full" : ""}"><span data-width="${pct}"></span></div>${reports}
        ${row.proposal ? html`<button class="chip warn" type="button" data-action="goto" data-tab="approvals">${icon("bell")}Waiting for a technician: ${row.proposal} (see Approvals)</button>` : ""}`,
    });
  }

  function paintStatus() {
    const services = (state.status || {}).services || [];
    const rank = { outage: 0, degraded: 1 };
    const sorted = services.slice().sort((a, b) => (rank[a.state] ?? 2) - (rank[b.state] ?? 2));
    const broken = services.filter((s) => s.state === "degraded" || s.state === "outage").length;
    paint(region("status"), html`
      <div class="section-label">Live service status <small>${services.length} services checked live · ${broken} with a known issue · refreshes every 20 s</small></div>
      ${services.length ? html`<div class="services">${sorted.map((s) => {
        const st = LIVE_STATES.includes(s.state) ? s.state : "unknown";
        return html`<div class="service ${st}"><div class="service-top"><span class="dot ${st}" title="${st}"></span><b>${s.service}</b>${s.demo ? chip("demo", "cyan") : ""}${s.stale ? chip("stale") : ""}</div><p>${clip(s.summary, 160)}</p></div>`;
      })}</div>` : html`<div class="skeleton"></div>`}`);
  }

  async function resolve(number) {
    const result = await api(`/admin/incidents/${enc(number)}/resolve`, { method: "POST",
      body: { technician_id: state.technician, note: drafts[`resolve-${number}`] || "" } });
    delete drafts[`resolve-${number}`];
    toast(`${number} resolved.`, "ok");
    if (result.notified) {
      toast(`Texted ${plural(result.notified, "affected employee")}; closed ${plural(result.resolved_children.length, "linked ticket")}.`, "info");
    }
  }

  // --- tickets ------------------------------------------------------------------------------------

  const prio = (p) => ([1, 2, 3, 4].includes(p) ? p : 3);
  const TICKETS = [
    { label: "Number", cell: (t) => html`${t.is_major ? html`<span class="star" title="Major incident">★</span> ` : ""}<span class="mono">${t.number}</span>`, cls: "nowrap" },
    { label: "P", cell: (t) => html`<span class="prio p${prio(t.priority)}">P${t.priority}</span>` },
    { label: "State", cell: (t) => chip(words(t.state), STATE_TONE[t.state]) },
    { label: "Summary", cell: (t) => t.short_description, cls: "wide" },
    { label: "Service", cell: (t) => (t.service ? serviceName(t.service) : "") },
    { label: "Caller", cell: (t) => (t.employee_id ? person(t.employee_id) : "") },
    { label: "Location", cell: (t) => t.location || "" },
    { label: "Major incident", cell: (t) => (t.parent_number ? html`<span class="mono">${t.parent_number}</span>` : ""), cls: "nowrap" },
    { label: "Opened", cell: (t) => when(t.created_at), cls: "nowrap" },
  ];

  async function loadTickets() {
    const number = state.selected.tickets;
    const [list, detail] = await Promise.all([
      api("/admin/incidents", { params: { open_only: $("#tickets-open").checked, limit: 300 } }),
      number ? api(`/admin/incidents/${enc(number)}`).catch(missing) : null,
    ]);
    state.tickets = list.incidents;
    state.ticketDetail = detail;
    renderTickets();
  }

  function renderTickets() {
    const query = $("#tickets-search").value.trim().toLowerCase();
    const text = (t) => [t.number, t.short_description, t.service, serviceName(t.service), who(t.employee_id),
      t.location, t.state, t.parent_number].join(" ").toLowerCase();
    const rows = query ? state.tickets.filter((t) => text(t).includes(query)) : state.tickets;
    const pick = { kind: "tickets", id: (t) => t.number, current: state.selected.tickets };
    paint(region("tickets"), html`<div class="split">
      ${card({ title: plural(rows.length, "ticket"), ic: "ticket", cls: "flush",
        aside: query ? chip(`matching “${clip(query, 24)}”`) : "",
        body: rows.length ? table(TICKETS, rows, { pick, scroll: "tickets", tall: true }) : empty("No tickets match.", "search") })}
      <div class="sticky">${state.ticketDetail ? ticketDetail(state.ticketDetail) : hint("Click a ticket to see its details and work notes, or to resolve it.")}</div>
    </div>`);
  }

  function ticketDetail(t) {
    const open = !["resolved", "closed"].includes(t.state);
    const notes = t.notes || [];
    const children = t.children || [];
    const facts = [...new Set([`P${t.priority}`, t.is_major ? "major incident" : t.ticket_type, words(t.category),
      t.service ? serviceName(t.service) : "no service", t.location || "—"])];
    const link = (number) => html`<a href="#tickets" class="mono" data-action="pick" data-kind="tickets" data-id="${number}">${number}</a>`;
    return card({
      title: html`<span class="mono">${t.number}</span> · ${t.short_description}`,
      ic: t.is_major ? "bolt" : "ticket", tone: t.is_major && open ? "bad" : "",
      aside: chip(words(t.state), STATE_TONE[t.state]),
      body: html`
        <p class="meta">${facts.join(" · ")} · opened ${when(t.created_at)} via ${t.channel}</p>
        <dl class="kv">
          ${t.employee_id ? html`<dt>Caller</dt><dd>${who(t.employee_id)}</dd>` : ""}
          ${t.parent_number ? html`<dt>Part of</dt><dd>major incident ${link(t.parent_number)}</dd>` : ""}
          ${t.description ? html`<dt>Details</dt><dd class="prose">${t.description}</dd>` : ""}
        </dl>
        ${children.length ? html`<div><span class="label">Linked reports (${children.length})</span><ul class="bullets">
          ${children.map((c) => html`<li>${link(c.number)} · ${who(c.employee_id)} · ${words(c.state)}</li>`)}</ul></div>` : ""}
        <div><span class="label">Work notes</span>${notes.length ? html`<ul class="list-plain">${notes.map((n) => html`
          <li>${icon("message")}<div><div class="prose">${n.note}</div><div class="meta">${n.author} · ${when(n.created_at)}</div></div></li>`)}</ul>`
          : html`<p class="meta">No notes yet.</p>`}</div>
        ${open ? html`<input class="input" data-draft="resolve-${t.number}" placeholder="Resolution note" aria-label="Resolution note">
          <button class="btn primary block" type="button" data-action="resolve" data-number="${t.number}">${icon("check")}${t.is_major ? "Resolve major incident and text everyone affected" : "Resolve"}</button>` : ""}`,
    });
  }

  // --- phones -------------------------------------------------------------------------------------

  const MESSAGES = [
    { label: "To", cell: (m) => person(m.employee_id) },
    { label: "How", cell: (m) => chip(m.channel, m.channel === "sms" ? "info" : "cyan", m.channel === "sms" ? "message" : "mail") },
    { label: "Message", cell: (m) => html`<span class="prose">${m.body}</span>`, cls: "wide" },
    { label: "When", cell: (m) => when(m.created_at), cls: "nowrap" },
  ];

  async function loadPhones() {
    const id = $("#phone-of").value;
    const [mine, all] = await Promise.all([
      api("/admin/messages", { params: { employee_id: id, limit: 30 } }),
      api("/admin/messages", { params: { limit: 50 } }),
    ]);
    const person = state.employees[id] || {};
    const inbox = mine.messages;
    const latest = inbox.find((m) => CODE.test(m.body));
    const code = latest ? latest.body.match(CODE)[1] : "";
    const bubble = (m) => html`<div class="bubble ${m.channel === "email" ? "email" : ""}"><div class="prose">${m.body}</div>
      <div class="meta">${icon(m.channel === "email" ? "mail" : "message")}${m.channel} · ${when(m.created_at)}</div></div>`;
    paint(region("phones"), html`<div class="phone-wrap">
      <div class="phone" aria-label="${person.full_name || id}'s phone"><div class="phone-notch"></div><div class="phone-screen">
        <div class="phone-status"><span>${person.mobile || "—"}</span><span>${person.email || ""}</span></div>
        <div class="otp"><span class="label">Latest verification code</span>
          ${code ? html`<div class="otp-digits" aria-label="${code.split("").join(" ")}">${code.split("").map((d) => html`<span>${d}</span>`)}</div>
            <p class="meta">Texted ${when(latest.created_at)} · read it out digit by digit</p>` : html`<p class="meta">No code texted yet.</p>`}</div>
        <div class="bubbles" data-scroll="bubbles">${inbox.length ? inbox.map(bubble) : html`<p class="meta">No messages yet.</p>`}</div>
      </div></div>
      ${card({ title: "Every message sent", ic: "mail", cls: "flush", aside: chip(String(all.messages.length)),
        body: all.messages.length ? table(MESSAGES, all.messages, { scroll: "messages", tall: true }) : empty("Nothing sent yet.") })}
    </div>`);
  }

  // --- calls --------------------------------------------------------------------------------------

  const CALLS = [
    { label: "Call", cell: (s) => html`<span class="mono" title="${s.conversation_id}">${clip(s.conversation_id, 22)}</span>`, cls: "nowrap" },
    { label: "Caller", cell: (s) => s.full_name || html`<span class="meta">not identified</span>` },
    { label: "Verified", cell: (s) => (s.verified_at ? chip("verified", "ok", "check") : "") },
    { label: "Locked", cell: (s) => (s.locked ? chip("locked", "bad", "lock") : "") },
    { label: "Last ticket", cell: (s) => (s.last_ticket ? html`<span class="mono">${s.last_ticket}</span>` : ""), cls: "nowrap" },
    { label: "Started", cell: (s) => when(s.created_at), cls: "nowrap" },
  ];

  async function loadCalls() {
    const cid = state.selected.calls;
    const [list, audit, review] = await Promise.all([
      api("/admin/sessions", { params: { limit: 50 } }),
      cid ? api("/admin/audit", { params: { conversation_id: cid, limit: 200 } }) : null,
      cid ? api(`/admin/reviews/${enc(cid)}`).catch(missing) : null,
    ]);
    const calls = list.sessions;
    const pick = { kind: "calls", id: (s) => s.conversation_id, current: cid };
    paint(region("calls"), html`<div class="split">
      ${card({ title: plural(calls.length, "recent call"), ic: "headset", cls: "flush",
        body: calls.length ? table(CALLS, calls, { pick, scroll: "calls", tall: true }) : empty("No calls yet. Open the talk link and call StormDesk.", "headset") })}
      <div class="sticky">${cid ? callDetail(cid, audit.entries.slice().reverse(), review) : hint("Click a call to replay every step the voice agent took.")}</div>
    </div>`);
  }

  function callDetail(cid, entries, review) {
    const verdict = review && VERDICT[review.verdict];
    const reviewBox = review
      ? html`<div class="callout ${verdict ? verdict.tone : "info"}">${icon("review")}<div><b>Review: ${verdict ? verdict.label : words(review.status)}</b>${review.headline ? html` · ${review.headline}` : ""}
          · <a href="#reviews" data-action="pick" data-kind="reviews" data-id="${cid}" data-goto="reviews">open in Reviews</a></div></div>`
      : html`<div class="row"><p class="meta grow">This call hasn't been reviewed yet.</p>
          <button class="btn small" type="button" data-action="review" data-id="${cid}">${icon("review")}Review this call now</button></div>`;
    const step = (e, i) => {
      const agentHint = (e.response || {}).agent_hint;
      return html`<details class="step" data-key="${cid}#${i}"><summary>
        <span class="ico ${e.ok ? "ok" : "warn"}">${icon(e.ok ? "check" : "alert")}</span><span class="time">${clock(e.ts)}</span>
        <span class="tool">${e.tool}</span>${chip(`${e.latency_ms} ms`)}</summary>
        <div class="step-body">${agentHint ? html`<div class="callout info">${icon("bulb")}<div>${agentHint}</div></div>` : ""}
          <div class="pair"><div><span class="label">Agent sent</span><pre class="json">${pretty(omit(e.request, "conversation_id"))}</pre></div>
          <div><span class="label">Server answered</span><pre class="json">${pretty(omit(e.response, "agent_hint"))}</pre></div></div></div></details>`;
    };
    return card({
      title: html`Timeline · <span class="mono">${clip(cid, 28)}</span>`, ic: "history", aside: chip(plural(entries.length, "step")),
      body: html`${reviewBox}${entries.length ? html`<div class="timeline">${entries.map(step)}</div>` : html`<p class="meta">No tool calls on this call.</p>`}`,
    });
  }

  async function startReview(cid) {
    await api(`/admin/reviews/${enc(cid)}/run`, { method: "POST" });
    toast(`Review of ${clip(cid, 24)} started. It takes about half a minute.`, "info");
  }

  // --- reviews ------------------------------------------------------------------------------------

  function verdictIcon(verdict) {
    const v = VERDICT[verdict];
    return v ? html`<span class="verdict-ico ${v.tone}" title="${v.label}">${icon(v.icon)}</span>`
      : html`<span class="verdict-ico muted" title="Not graded yet">${icon("clock")}</span>`;
  }

  const REVIEWS = [
    { label: "", cell: (r) => verdictIcon(r.verdict) },
    { label: "Caller", cell: (r) => (r.employee_id ? person(r.employee_id) : "—") },
    { label: "Headline", cell: (r) => r.headline || words(r.status), cls: "wide" },
    { label: "When", cell: (r) => when(r.call_started_at || r.created_at), cls: "nowrap" },
  ];

  async function loadReviews() {
    const cid = state.selected.reviews;
    const { reviews } = await api("/admin/reviews", { params: { limit: 50 } });
    const count = (verdict) => reviews.filter((r) => r.verdict === verdict).length;
    const picked = cid ? reviews.find((r) => r.conversation_id === cid) : null;
    const tile = (label, value, ic) => html`<div class="kpi static"><span class="kpi-label">${icon(ic)}${label}</span><span class="kpi-value">${value}</span></div>`;
    const pick = { kind: "reviews", id: (r) => r.conversation_id, current: cid };
    paint(region("reviews"), html`
      <div class="grid cols-4 tiles">${tile("Calls reviewed", reviews.length, "review")}${tile("Pass", count("pass"), "check")}
        ${tile("Attention", count("attention"), "alert")}${tile("Fail", count("fail"), "x")}</div>
      <div class="split">
        ${card({ title: "Reviewed calls", ic: "review", cls: "flush",
          body: reviews.length ? table(REVIEWS, reviews, { pick, scroll: "reviews", tall: true }) : empty("No reviews yet. Calls are reviewed a minute or two after they end.", "review") })}
        <div class="sticky">${picked ? reviewDetail(picked) : hint("Click a review to see its scorecard, rule checks and follow-ups.")}</div>
      </div>`);
  }

  function checks(rows, result, label, detail) {
    if (!rows.length) return html`<p class="meta">None.</p>`;
    return html`<div class="table-wrap"><table class="checks"><tbody>${rows.map((c) => {
      const [tone, ic] = RESULT[result(c)] || ["muted", "minus"];
      return html`<tr><td><span class="verdict-ico ${tone}" title="${words(result(c))}">${icon(ic)}</span></td><td><b>${label(c)}</b></td><td>${detail(c)}</td></tr>`;
    })}</tbody></table></div>`;
  }

  function reviewDetail(review) {
    const report = review.report || {};
    const score = report.scorecard || {};
    const resolution = report.resolution || {};
    const process = report.process || {};
    const experience = report.experience || {};
    const items = (report.follow_up || {}).items || [];
    const opinion = report.elevenlabs_opinion || {};
    const cid = review.conversation_id;
    const verdict = VERDICT[review.verdict];
    const scoreTile = (label, value, unit = "/5") => html`<div class="score"><span class="label">${label}</span><b>${value || "—"}</b>${value ? html`<small>${unit}</small>` : ""}</div>`;
    const follow = (item, i) => html`<div class="follow"><div><p><b>${words(item.owner)} · ${words(item.urgency)}:</b> ${item.action}</p><small>${item.reason}</small></div>
      ${item.ticket ? chip(item.ticket, "ok", "check") : html`<button class="btn small" type="button" data-action="followup" data-id="${cid}" data-index="${i}">${icon("ticket")}Create ticket</button>`}</div>`;
    const bullets = (list, cls, ic) => (list || []).map((x) => html`<li class="${cls}">${icon(ic)}<span>${x}</span></li>`);
    return card({
      title: html`${words(review.verdict || review.status).toUpperCase()} · ${review.employee_id ? who(review.employee_id) : "caller not identified"}`,
      ic: verdict ? verdict.icon : "clock", aside: verdict ? chip(verdict.label, verdict.tone) : chip(words(review.status)),
      body: html`
        ${score.headline ? html`<p class="headline">${score.headline}</p>` : ""}
        <div class="grid cols-4">${scoreTile("Resolution", score.resolution_score)}${scoreTile("Process", score.process_score)}
          ${scoreTile("Experience", score.experience_score)}${scoreTile("Call length", (report.metrics || {}).duration_s, " s")}</div>
        <div class="desks">${(report.desks || []).map((d, i) => html`${i ? html`<span class="arrow">→</span>` : ""}${chip(d, "info")}`)}</div>
        <p class="meta">Outcome: ${words(resolution.outcome || "—")} · model: <span class="mono">${review.model || "—"}</span> ·
          <a href="https://elevenlabs.io/app/agents/history/${enc(cid)}" target="_blank" rel="noopener noreferrer">ElevenLabs transcript</a></p>
        ${review.error ? html`<div class="callout warn">${icon("alert")}<div>Incomplete: ${review.error}</div></div>` : ""}
        ${(score.flags || []).map((f) => html`<div class="callout warn">${icon("flag")}<div>${f}</div></div>`)}
        <div><span class="label">Rule checks · from StormDesk's records</span>${checks(report.rule_checks || [], (c) => c.result, (c) => c.label, (c) => c.detail)}</div>
        <div><span class="label">Process review · AI</span>${checks(process.checks || [], (c) => c.verdict, (c) => words(c.name), (c) => c.evidence)}</div>
        ${(process.violations || []).map((x) => html`<div class="callout bad">${icon("x")}<div>Violation: ${x}</div></div>`)}
        ${(process.social_engineering_signals || []).map((x) => html`<div class="callout warn">${icon("eye")}<div>Caller behaviour: ${x}</div></div>`)}
        <div class="pair">
          <div><span class="label">What the caller needed</span><p>${resolution.caller_need || "—"}</p>
            ${(resolution.evidence || []).map((q) => html`<blockquote class="quote">${q}</blockquote>`)}</div>
          <div><span class="label">Caller experience</span><p>${experience.summary || "—"}</p>
            <ul class="list-plain">${bullets(experience.strengths, "good", "check")}${bullets(experience.issues, "poor", "x")}</ul></div>
        </div>
        <div><span class="label">Follow-ups (${items.length})</span>${items.length ? html`<div class="stack tight">${items.map(follow)}</div>` : html`<p class="meta">None needed.</p>`}</div>
        ${(score.coaching || []).length ? html`<div><span class="label">Coaching for the agent's instructions</span><ul class="list-plain">${bullets(score.coaching, "tip", "bulb")}</ul></div>` : ""}
        ${opinion.call_successful ? html`<p class="meta">For comparison, ElevenLabs' built-in analysis rated this call: ${opinion.call_successful}.</p>` : ""}`,
      foot: html`<button class="btn" type="button" data-action="review" data-id="${cid}">${icon("refresh")}Re-run review</button>`,
    });
  }

  async function followUp(cid, index) {
    const result = await api(`/admin/reviews/${enc(cid)}/follow-ups/${index}`, { method: "POST",
      body: { technician_id: state.technician } });
    toast(`Follow-up ticket ${result.ticket} created.`, "ok");
  }

  // --- drills -------------------------------------------------------------------------------------

  const OUTBOX = [
    { label: "Ref", cell: (e) => html`<span class="mono">${e.ref}</span>`, cls: "nowrap" },
    { label: "What", cell: (e) => e.kind },
    { label: "Status", cell: (e) => chip(e.status, e.status === "delivered" ? "ok" : "warn") },
    { label: "Ticket", cell: (e) => (e.result ? html`<span class="mono">${e.result}</span>` : "") },
    { label: "Tries", cell: (e) => e.attempts },
    { label: "Queued", cell: (e) => when(e.created_at), cls: "nowrap" },
  ];

  async function loadDrills() {
    const [chaos, outbox, demos] = await Promise.all([api("/admin/chaos"), api("/admin/outbox"), api("/admin/demo-outages")]);
    const serviceOptions = state.services.map((s) => html`<option value="${s.key}">${s.name}</option>`);
    const switches = Object.entries(chaos.descriptions).map(([flag, description]) => html`<label class="switch-row">
      <input type="checkbox" data-change="chaos" data-flag="${flag}"${chaos.flags[flag] ? trusted(" checked") : ""}><span class="toggle-ui"></span>
      <span><b>${DRILL[flag] || words(flag)}</b><small>${description}</small></span></label>`);
    paint(region("drills"), html`<div class="grid cols-2">
      <div class="stack">
        ${card({ title: "Failure switches", ic: "alert", body: html`<p class="meta">Break a dependency on purpose and watch StormDesk cope.</p><div class="switches">${switches}</div>` })}
        ${card({ title: "Outbox", ic: "inbox", cls: "flush", aside: chip(String(outbox.entries.length)),
          body: outbox.entries.length ? table(OUTBOX, outbox.entries) : empty("Empty. Tickets wait here while the ticket system is down.", "inbox"),
          foot: html`<button class="btn" type="button" data-action="housekeeping">${icon("refresh")}Deliver queued tickets now</button>` })}
      </div>
      <div class="stack">
        ${card({ title: "Demo outage", ic: "play", body: html`
          <p class="meta">Real outages happen at random. This one is labelled "demo" everywhere it appears.</p>
          <label class="field"><span>Service</span><select class="input" data-draft="demo_service">${serviceOptions}</select></label>
          <label class="field"><span>What's broken</span><input class="input" data-draft="demo_title"></label>
          <div class="field"><span>Impact</span><div class="segmented" role="radiogroup" aria-label="Impact">
            ${["outage", "degraded"].map((v) => html`<label><input type="radio" name="demo_impact" value="${v}" data-draft="demo_impact"><span>${v}</span></label>`)}</div></div>
          <div class="row"><button class="btn primary" type="button" data-action="demo-start">${icon("play")}Start demo outage</button>
            ${demos.demo_outages.map((d) => html`<button class="btn" type="button" data-action="demo-clear" data-service="${d.service_key}">${icon("x")}Clear: ${serviceName(d.service_key)}</button>`)}</div>` })}
        ${card({ title: "Set up a ticket storm", ic: "storm", body: html`
          <p class="meta">Open reports from colleagues, so the next caller about the same thing tips it over.</p>
          <div class="pair"><label class="field"><span>Service</span><select class="input" data-draft="storm_service">${serviceOptions}</select></label>
            <label class="field"><span>Office</span><select class="input" data-draft="storm_location">${LOCATIONS.map((l) => html`<option value="${l}">${l}</option>`)}</select></label></div>
          <label class="field"><span>Reports</span><select class="input" data-draft="storm_count">${["1", "2", "3"].map((n) => html`<option value="${n}">${n}</option>`)}</select></label>
          <button class="btn primary" type="button" data-action="storm-add">${icon("plus")}Add reports</button>` })}
        ${card({ title: "Start over", ic: "trash", tone: "bad", body: html`
          <label class="check"><input type="checkbox" data-draft="reset_confirm">I understand this wipes every ticket, call, approval and review</label>
          <p class="meta">A backup of the current data is saved first. To bring it back: stop the backend, then run <code>uv run python -m stormdesk.seed --restore</code></p>
          <button class="btn danger" type="button" id="reset-btn" data-action="reset"${drafts.reset_confirm ? "" : trusted(" disabled")}>${icon("trash")}Reset practice data</button>` })}
      </div></div>`);
  }

  async function setDrill(input) {
    const { flag } = input.dataset;
    const enabled = input.checked;
    input.disabled = true;
    try {
      const result = await api("/admin/chaos", { method: "POST", body: { flag, enabled } });
      toast(`${DRILL[flag] || flag}: ${enabled ? "ON" : "off"}.`, enabled ? "warn" : "ok");
      const delivered = ((result.delivered_from_outbox || {}).delivered || []);
      if (delivered.length) toast(`Delivered from the outbox: ${delivered.map((d) => `${d.ref} → ${d.result}`).join(", ")}`, "info");
    } catch (err) {
      input.checked = !enabled;
      toast(err.message, "bad");
    } finally {
      input.disabled = false;
    }
    await refreshNow();
  }

  async function startDemo() {
    const body = { service: drafts.demo_service, title: (drafts.demo_title || "").trim() || "Users unable to connect",
      impact: drafts.demo_impact || "outage" };
    await api("/admin/demo-outage", { method: "POST", body });
    state.status = null;
    toast(`Demo outage started on ${serviceName(body.service)}.`, "warn");
  }

  async function clearDemo(key) {
    await api(`/admin/demo-outage/${enc(key)}`, { method: "DELETE" });
    state.status = null;
    toast(`Demo outage on ${serviceName(key)} cleared.`, "ok");
  }

  async function addStorm() {
    const body = { service: drafts.storm_service, location: drafts.storm_location, count: Number(drafts.storm_count) || 2 };
    await api("/admin/demo-storm", { method: "POST", body });
    toast(`Opened ${plural(body.count, `${serviceName(body.service)} report`)} from ${body.location}.`, "ok");
  }

  async function housekeeping() {
    const result = await api("/admin/housekeeping", { method: "POST" });
    toast(`Housekeeping ran: delivered ${plural((result.delivered || []).length, "queued ticket")}, `
      + `expired ${plural((result.expired_approvals || []).length, "stale approval")}.`, "ok");
  }

  async function resetData() {
    if (!drafts.reset_confirm) return;
    const result = await api("/admin/reset", { method: "POST", body: { confirm: true } });
    drafts.reset_confirm = false;
    state.selected = { tickets: null, calls: null, reviews: null };
    state.status = null;
    state.seenPending = 0;
    await loadEmployees();
    toast(result.backup ? `Practice data reset. The old data was backed up first (${result.backup}).`
      : "Practice data reset.", "ok");
  }

  // --- tabs and refreshing ------------------------------------------------------------------------

  const LOADERS = { approvals: loadApprovals, storm: loadStorm, tickets: loadTickets, phones: loadPhones,
    calls: loadCalls, reviews: loadReviews, drills: loadDrills };
  let timer = null;
  let generation = 0;

  async function loadTab(tab = state.tab) {
    try {
      await LOADERS[tab]();
      panelError(tab, null);
    } catch (err) {
      if (err.status !== 0 && err.status !== 401) panelError(tab, err.message);
    }
  }

  function panelError(tab, message) {
    const panel = $(`#panel-${tab}`);
    let box = $(".panel-error", panel);
    if (!message) { if (box) box.remove(); return; }
    if (!box) {
      box = document.createElement("div");
      box.className = "callout bad panel-error";
      $(".panel-head", panel).after(box);
    }
    box.textContent = `Couldn't refresh this tab: ${message}`;
  }

  function schedule() {
    clearTimeout(timer);
    const mine = ++generation;
    const every = TABS.find((t) => t.id === state.tab).every;
    const run = async () => {
      await loadTab();
      if (mine === generation) timer = setTimeout(run, document.hidden ? 15000 : every);
    };
    run();
  }

  async function refreshNow() {
    await Promise.all([loadTab(), loadOverview().catch(() => {})]);
  }

  function showTab(id) {
    if (!LOADERS[id]) id = "approvals";
    state.tab = id;
    for (const t of TABS) {
      $(`#tab-${t.id}`).setAttribute("aria-selected", String(t.id === id));
      $(`#panel-${t.id}`).hidden = t.id !== id;
    }
    keep("localStorage", "stormdesk-tab", id);
    schedule();
  }

  async function overviewLoop() {
    await loadOverview().catch(() => {});
    setTimeout(overviewLoop, document.hidden ? 15000 : 3000);
  }

  // --- banners, toasts, the admin key --------------------------------------------------------------

  let offline = false;
  function online(ok) {
    if (ok === !offline) return;
    offline = !ok;
    const live = $("#live");
    live.classList.toggle("off", offline);
    live.lastElementChild.textContent = offline ? "Offline" : "Live";
    const banner = $("#banner");
    banner.hidden = !offline;
    banner.textContent = offline ? OFFLINE : "";
  }

  function toast(message, tone = "info", ic = null) {
    const box = $("#toasts");
    const el = document.createElement("div");
    el.className = `toast ${tone}`;
    el.setAttribute("role", tone === "bad" ? "alert" : "status");
    el.innerHTML = part(html`${icon(ic || TOAST_ICON[tone] || "info")}<div></div>`);
    el.lastElementChild.textContent = message;
    box.append(el);
    while (box.children.length > 4) box.firstElementChild.remove();
    setTimeout(() => {
      el.classList.add("leaving");
      setTimeout(() => el.remove(), 300);
    }, tone === "bad" ? 9000 : 5000);
  }

  let asking = false;
  function askForKey() {
    if (asking) return;
    asking = true;
    adminKey = "";
    keep("sessionStorage", "stormdesk-admin-key", null);
    $("#keyinput").value = "";
    $("#keydialog").showModal();
  }

  // --- wiring -------------------------------------------------------------------------------------

  async function pick(el) {
    const { kind, id } = el.dataset;
    state.selected[kind] = id;
    if (kind === "tickets") state.ticketDetail = null;
    if (el.dataset.goto && el.dataset.goto !== state.tab) location.hash = el.dataset.goto;
    else await loadTab();
  }

  const ACTIONS = {
    pick,
    goto: (el) => { location.hash = el.dataset.tab; },
    refresh: () => loadTab(),
    decide: (el) => decide(el.dataset.id, el.dataset.approve === "1"),
    resolve: (el) => resolve(el.dataset.number),
    review: (el) => startReview(el.dataset.id),
    followup: (el) => followUp(el.dataset.id, Number(el.dataset.index)),
    housekeeping,
    "demo-start": startDemo,
    "demo-clear": (el) => clearDemo(el.dataset.service),
    "storm-add": addStorm,
    reset: resetData,
  };
  // These only look; everything else changes something, so the screen refreshes after it.
  const LOOKING = new Set(["pick", "goto", "refresh"]);

  async function act(el) {
    const name = el.dataset.action;
    const button = el.tagName === "BUTTON" ? el : null;
    if (button) { button.disabled = true; button.classList.add("busy"); }
    try {
      await ACTIONS[name](el);
      if (!LOOKING.has(name)) await refreshNow();
    } catch (err) {
      toast(err.message || String(err), "bad");
    } finally {
      if (button) { button.disabled = false; button.classList.remove("busy"); }
    }
  }

  function remember(event) {
    const el = event.target;
    const key = el.dataset && el.dataset.draft;
    if (!key) return;
    drafts[key] = el.type === "checkbox" ? el.checked : el.value;
    if (key === "reset_confirm") $("#reset-btn").disabled = !el.checked;
  }

  function wire() {
    $("#tabs").innerHTML = part(TABS.map((t) => html`<button class="tab" role="tab" type="button" id="tab-${t.id}" data-tab="${t.id}"
      aria-controls="panel-${t.id}" aria-selected="false">${icon(t.icon)}<span>${t.label}</span><span class="count" data-count="${t.id}" hidden></span></button>`));
    for (const t of TABS) $(`#panel-${t.id}`).setAttribute("aria-labelledby", `tab-${t.id}`);

    document.addEventListener("click", (event) => {
      const tab = event.target.closest(".tab");
      if (tab) { location.hash = tab.dataset.tab; return; }
      const el = event.target.closest("[data-action]");
      if (!el || el.disabled || !ACTIONS[el.dataset.action]) return;
      event.preventDefault();
      act(el);
    });
    document.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && event.target.matches("tr.pick")) {
        event.preventDefault();
        act(event.target);
      }
    });
    document.addEventListener("input", (event) => {
      remember(event);
      if (event.target.id === "tickets-search") renderTickets();
    });
    document.addEventListener("change", (event) => {
      const el = event.target;
      remember(event);
      if (el.dataset.change === "chaos") setDrill(el);
      else if (el.id === "technician") {
        state.technician = el.value;
        keep("localStorage", "stormdesk-technician", el.value);
        loadTab();
      } else if (el.id === "phone-of") {
        keep("localStorage", "stormdesk-phone", el.value);
        loadTab();
      } else if (el.id === "tickets-open") loadTab();
    });
    document.addEventListener("toggle", (event) => {
      const key = event.target.dataset && event.target.dataset.key;
      if (key) { if (event.target.open) openSteps.add(key); else openSteps.delete(key); }
    }, true);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) schedule(); });
    window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));
    $("#keyform").addEventListener("submit", (event) => {
      event.preventDefault();
      adminKey = $("#keyinput").value.trim();
      keep("sessionStorage", "stormdesk-admin-key", adminKey);
      $("#keydialog").close();
    });
    $("#keydialog").addEventListener("close", () => {
      asking = false;
      boot();
    });
    setInterval(() => fillTimes(), 20000);
  }

  let started = false;
  async function boot() {
    try {
      await loadEmployees();
    } catch (err) {
      if (err.status === 401) return; // the key dialog is open; closing it boots again
      if (err.status !== 0) {
        const banner = $("#banner");
        banner.hidden = false;
        banner.textContent = `StormDesk refused the console: ${err.message}`;
      }
      setTimeout(boot, 5000);
      return;
    }
    if (!offline) $("#banner").hidden = true;
    if (started) return refreshNow();
    started = true;
    overviewLoop();
    showTab(location.hash.slice(1) || stored("localStorage", "stormdesk-tab") || "approvals");
  }

  wire();
  boot();
})();
