(() => {
  const root = root_element;
  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const url = (type, name) => `/app/${type.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(name)}`;
  const active = ["Assigned", "Accepted", "In Progress"];
  const unfinished = ["Approved", "Cancelled"];
  const states = ["Assigned", "Accepted", "In Progress", "Submitted", "Approved", "Rejected", "Cancelled"];
  const colors = ["#8ea7b1", "#759fb8", "#378ca1", "#d1a45f", "#45977e", "#bc7272", "#b3babc"];
  let tab = "overdue", generation = 0, model = null;
  const counties = "Mombasa|Kwale|Kilifi|Tana River|Lamu|Taita Taveta|Garissa|Wajir|Mandera|Marsabit|Isiolo|Meru|Tharaka Nithi|Embu|Kitui|Machakos|Makueni|Nyandarua|Nyeri|Kirinyaga|Murang'a|Kiambu|Turkana|West Pokot|Samburu|Trans Nzoia|Uasin Gishu|Elgeyo Marakwet|Nandi|Baringo|Laikipia|Nakuru|Narok|Kajiado|Kericho|Bomet|Kakamega|Vihiga|Bungoma|Busia|Siaya|Kisumu|Homa Bay|Migori|Kisii|Nyamira|Nairobi".split("|").sort();
  $("#ops-county").insertAdjacentHTML("beforeend", counties.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join(""));
  function filters(kind) {
    if (kind === "scout_applications") return {type: "Scout Application", f: [["status", "=", "Pending"]]};
    if (kind === 'recurring_review') return {type:'DD Recurring Plan',f:[['status','=','Pending review']]};
    if (kind === 'recurring_visits') return {type:'DD Recurring Occurrence',f:[['status','in',['Awaiting access','Access confirmed']],['due_date','<=',frappe.datetime.add_days(frappe.datetime.get_today(),14)]]};
    const globalLists = { quotations: "DD Quotation", scout_submissions: "FP Task Response", client_reports: "DD Service Report" };
    if (globalLists[kind]) return { type: globalLists[kind], f: [] };
    const county = $("#ops-county").value;
    const scout = ["available", "busy", "leave", "inactive", "scouts"].includes(kind);
    const type = kind === "diaspora_requests" ? "Diaspora Request" : scout ? "Scout Profile" : ["waiting", "requests"].includes(kind) ? "Field Request" : "Field Task";
    const f = county ? [[scout ? "base_county" : "county", kind === "diaspora_requests" ? "like" : "=", kind === "diaspora_requests" ? `%${county}%` : county]] : [];
    if (scout && kind !== "scouts") f.push(["access_status", "!=", "Deactivated"]);
    if (kind === "waiting") f.push(["status", "=", "Awaiting Assignment"]);
    if (kind === "active") f.push(["status", "in", active]);
    if (kind === "overdue") f.push(["status", "not in", unfinished], ["due_at", "<", frappe.datetime.now_datetime()]);
    if (["submitted", "approved"].includes(kind)) f.push(["status", "=", kind === "submitted" ? "Submitted" : "Approved"]);
    if (["available", "busy", "leave"].includes(kind)) f.push(["availability_status", "=", {available:"Available", busy:"Busy", leave:"On Leave"}[kind]]);
    if (kind === "inactive") f.push(["activity_status", "=", "Inactive"]);
    return {type, f};
  }
  function openList(kind) {
    const {type, f} = filters(kind);
    frappe.route_options = Object.fromEntries(f.map(([key, op, value]) => [key, op === "=" ? value : [op, value]]));
    frappe.set_route("List", type);
  }
  const date = value => value ? frappe.datetime.str_to_user(value.slice(0, 10)) : "Flexible";
  const list = (kind, fields, order_by, limit = 6) => {
    const {type, f} = filters(kind);
    return frappe.xcall("frappe.desk.reportview.get_list", {doctype:type, fields, filters:f, order_by, limit});
  };
  async function waitingQueue() {
    const {type, f} = filters("waiting");
    const rows = [];
    for (let start = 0; ; start += 100) {
      const page = await frappe.xcall("frappe.desk.reportview.get_list", {doctype:type, fields:["name", "project_title", "project_number", "request_type", "county", "deadline", "priority", "alignment_review", "creation"], filters:f, order_by:"creation asc", limit:100, start});
      rows.push(...page);
      if (page.length < 100) return rows;
    }
  }
  function renderAttention() {
    if (!model) return;
    const rows = model[tab];
    $("[data-rows=attention]").innerHTML = rows.length ? rows.map(t => `<div class="task-row"><div><a class="project-link" href="${url("Field Task", t.name)}">${esc(t.project_title || t.name)}</a><span class="subline">${esc(t.name)} · ${esc(t.county || "County unconfirmed")} · Scout ${esc(t.scout_profile || "unassigned")}</span><span class="badge ${tab === "overdue" ? "review" : "ready"}">${esc(t.status)}${tab === "overdue" ? ` · Due ${esc(date(t.due_at))}` : ""}</span></div><a class="row-action" href="${url("Field Task", t.name)}">${tab === "overdue" ? "Follow up" : "Review evidence"} ↗</a></div>`).join("") : `<div class="empty">${tab === "overdue" ? "No overdue tasks in this coverage. Fieldwork is on track." : "No evidence waiting for review in this coverage."}</div>`;
  }
  function render(data) {
    model = data;
    for (const [key, value] of Object.entries(data.counts)) root.querySelectorAll(`[data-count="${key}"]`).forEach(el => el.textContent = Number(value).toLocaleString());
    $("[data-rows=queue]").innerHTML = data.queue.length ? data.queue.map(r => {
      const review = r.alignment_review || !r.project_number || !r.county;
      const late = r.deadline && r.deadline < frappe.datetime.get_today();
      return `<tr><td><a class="project-link" href="${url("Field Request", r.name)}">${esc(r.project_title || r.request_type || "Field request")}</a><span class="subline">${esc(r.name)}${r.project_number ? ` · Project ${esc(r.project_number)}` : ""}${["High", "Urgent"].includes(r.priority) ? `<span class="badge ${r.priority.toLowerCase()}">${esc(r.priority)}</span>` : ""}</span></td><td>${esc(r.county || "Unconfirmed")}</td><td class="${late ? "due-late" : ""}">${esc(date(r.deadline))}</td><td><span class="badge ${review ? "review" : "ready"}">${review ? "Scope review" : "Ready to assign"}</span><a class="row-action" href="${url("Field Request", r.name)}">${review ? "Review project" : "Assign scouts"} ↗</a></td></tr>`;
    }).join("") : '<tr><td colspan="4" class="empty">No projects waiting for assignment in this coverage.</td></tr>';
    const total = data.counts.available + data.counts.busy + data.counts.leave;
    $(".capacity-bar").innerHTML = ["available", "busy", "leave"].map(k => `<span class="${k}" style="width:${total ? data.counts[k] / total * 100 : 0}%"></span>`).join("");
    $(".capacity-bar").setAttribute("aria-label", `${data.counts.available} available, ${data.counts.busy} busy, ${data.counts.leave} on leave`);
    $("[data-rows=scouts]").innerHTML = data.scouts.length ? data.scouts.map(s => `<a class="scout-row" href="${url("Scout Profile", s.name)}"><span class="avatar" aria-hidden="true">${esc((s.scout_name || s.name).split(/\s+/).map(w => w[0]).slice(0,2).join("").toUpperCase())}</span><div><span class="scout-name">${esc(s.scout_name || s.name)}</span><span class="subline">${esc(s.base_county || "County unconfirmed")}${s.activity_status === "Inactive" ? '<span class="inactive-note">· Inactive</span>' : ""}</span></div><span class="badge ready">Available</span></a>`).join("") : '<div class="empty">No scouts marked available in this coverage.</div>';
    const max = Math.max(1, ...data.pipeline);
    $("[data-rows=pipeline]").innerHTML = states.map((s, i) => `<button class="pipeline-row" data-state="${esc(s)}" aria-label="${esc(s)}: ${data.pipeline[i]} tasks"><span>${esc(s)}</span><span class="track"><i style="width:${data.pipeline[i] / max * 100}%;background:${colors[i]}"></i></span><b>${data.pipeline[i]}</b></button>`).join("");
    renderAttention();
  }
  async function load() {
    const version = ++generation;
    $(".ops").setAttribute("aria-busy", "true");
    $(".error").hidden = true;
    $(".updated").textContent = "Updating live data…";
    $("[data-action=refresh]").disabled = true;
    try {
      const keys = ["quotations", "scout_submissions", "client_reports", "diaspora_requests", "waiting", "active", "overdue", "submitted", "available", "busy", "leave", "inactive", "approved"];
      const results = await Promise.allSettled([
        ...keys.map(k => {const {type, f} = filters(k); return frappe.db.count(type, {filters:f});}),
        ...states.map(status => {const {f} = filters("tasks"); return frappe.db.count("Field Task", {filters:[...f, ["status", "=", status]]});}),
        waitingQueue(),
        list("available", ["name", "scout_name", "base_county", "activity_status"], "scout_name asc", 3),
        list("overdue", ["name", "task_number", "project_title", "county", "scout_profile", "status", "due_at"], "due_at asc", 4),
        list("submitted", ["name", "task_number", "project_title", "county", "scout_profile", "status", "due_at"], "submitted_at asc", 4),
      ]);
      if (version !== generation) return;
      if (results.some(r => r.status === "rejected")) throw new Error("Data unavailable");
      const values = results.map(r => r.value);
      const start = keys.length + states.length;
      const waiting = values[start];
      waiting.sort((a,b) => ({Urgent:0,High:1,Normal:2,Low:3}[a.priority] ?? 2) - ({Urgent:0,High:1,Normal:2,Low:3}[b.priority] ?? 2) || (a.deadline || "9999").localeCompare(b.deadline || "9999") || a.creation.localeCompare(b.creation));
      render({counts:Object.fromEntries(keys.map((k,i) => [k,values[i]])),pipeline:values.slice(keys.length,start),queue:waiting.slice(0,6),scouts:values[start+1],overdue:values[start+2],submitted:values[start+3]});
      $(".updated").textContent = `Updated ${frappe.datetime.now_datetime().slice(11,16)} · site time`;
    } catch (error) {
      if (version !== generation) return;
      model = null;
      root.querySelectorAll("[data-count]").forEach(el => el.textContent = "—");
      root.querySelectorAll("[data-rows]").forEach(el => el.innerHTML = el.tagName === "TBODY" ? '<tr><td colspan="4" class="empty">Data unavailable. Try refreshing.</td></tr>' : '<div class="empty">Data unavailable. Try refreshing.</div>');
      $(".capacity-bar").innerHTML = "";
      $(".error").textContent = "Some operations data could not be loaded. Check your connection and access to the request, task, scout, quotation, submission and report lists, then refresh.";
      $(".error").hidden = false;
      $(".updated").textContent = "Update failed";
    } finally {
      if (version === generation) {$(".ops").setAttribute("aria-busy", "false"); $("[data-action=refresh]").disabled = false;}
    }
  }
  root.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.list) openList(button.dataset.list);
    if (button.dataset.action === "refresh") load();
    if (button.dataset.action === "recurring_report") frappe.set_route("query-report", "Recurring Check Schedule");
    if (button.dataset.action === "create") frappe.new_doc("Field Request", {source:"Manual"});
    if (button.dataset.tab) {
      tab = button.dataset.tab;
      root.querySelectorAll("[data-tab]").forEach(el => el.setAttribute("aria-selected", String(el.dataset.tab === tab)));
      renderAttention();
    }
    if (button.classList.contains("attention-all")) openList(tab);
    if (button.dataset.state) {
      const {f} = filters("tasks");
      frappe.route_options = Object.fromEntries([...f, ["status", "=", button.dataset.state]].map(([key,,value]) => [key,value]));
      frappe.set_route("List", "Field Task");
    }
  });
  $("#ops-county").addEventListener("change", load);
  load();
})();
