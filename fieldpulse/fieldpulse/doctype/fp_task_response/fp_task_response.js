frappe.ui.form.on("FP Task Response", {
  async refresh(frm) {
    if (frm.is_new() || !["Field Operations Coordinator", "System Manager"].some(r => frappe.user.has_role(r))) return;
    const wrapper = frm.fields_dict.submission_review.$wrapper;
    const esc = value => frappe.utils.escape_html(String(value ?? ""));
    const parse = (raw, fallback = {}) => {
      try { return typeof raw === "string" ? JSON.parse(raw) ?? fallback : raw ?? fallback; } catch { return fallback; }
    };
    const badge = (label, tone = "neutral") => `<span class="fp-review-badge fp-review-${tone}">${esc(label)}</span>`;
    const text = value => `<div class="fp-review-text">${esc(value)}</div>`;
    const humanize = key => key.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
    const structured = value => {
      if (value == null || value === "") return text("Not recorded");
      if (Array.isArray(value)) return value.length ? `<ul class="fp-review-list">${value.map(item => `<li>${structured(item)}</li>`).join("")}</ul>` : text("None recorded");
      if (typeof value === "object") return `<dl class="fp-review-values">${Object.entries(value).map(([key, item]) => `<div><dt>${esc(humanize(key))}</dt><dd>${structured(item)}</dd></div>`).join("")}</dl>`;
      return text(typeof value === "boolean" ? value ? "Yes" : "No" : value);
    };
    const block = (title, value) => `<div class="fp-review-field"><div class="fp-review-label">${esc(title)}</div>${structured(value)}</div>`;
    const card = (title, body, status = "") => `<section class="fp-review-card"><header><h4>${esc(title)}</h4>${status}</header>${body}</section>`;
    const styles = `<style>
      .fp-review { color:var(--text-color); }
      .fp-review .fp-review-card { border:1px solid var(--border-color); border-radius:10px; padding:20px; margin:0 0 18px; background:var(--card-bg,var(--fg-color)); }
      .fp-review header { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
      .fp-review h4 { font-size:16px; line-height:1.5; margin:0; flex:1; min-width:180px; }
      .fp-review h5 { font-size:13px; font-weight:600; margin:0 0 12px; }
      .fp-review .fp-review-field { margin:12px 0; }
      .fp-review .fp-review-label,.fp-review dt { font-size:12px; font-weight:600; color:var(--text-muted); margin-bottom:5px; }
      .fp-review .fp-review-text { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.65; }
      .fp-review .fp-review-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr)); gap:12px; }
      .fp-review .fp-review-evidence { border:1px solid var(--border-color); border-radius:8px; padding:14px; min-width:0; }
      .fp-review .fp-review-evidence-heading { display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
      .fp-review .fp-review-meta { font-size:12px; color:var(--text-muted); margin:8px 0; overflow-wrap:anywhere; }
      .fp-review .fp-review-evidence-section { border-top:1px solid var(--border-color); padding-top:16px; margin-top:20px; }
      .fp-review .fp-review-badge { display:inline-block; font-size:12px; border-radius:5px; padding:4px 8px; background:var(--subtle-fg); color:var(--text-color); }
      .fp-review .fp-review-success { background:var(--green-100); color:var(--green-800); }
      .fp-review .fp-review-warning { background:var(--yellow-100); color:var(--yellow-800); }
      .fp-review .fp-review-notice { border-left:3px solid var(--yellow-500); padding:1px 12px; margin:12px 0; background:var(--subtle-fg); }
      .fp-review details { margin:12px 0; }
      .fp-review summary { cursor:pointer; font-weight:500; }
      .fp-review .fp-review-values { margin:8px 0; padding-left:12px; border-left:2px solid var(--border-color); }
      .fp-review .fp-review-answer { background:var(--subtle-fg,#f5f7fa); border-radius:8px; padding:4px 16px; margin-top:16px; }
      .fp-review .fp-review-section-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:28px 0 16px; }
      .fp-review .fp-review-overview { border-bottom:1px solid var(--border-color); margin-bottom:16px; padding-bottom:12px; }
      .fp-review .fp-review-overview .fp-review-text { font-size:18px; font-weight:600; }
      .fp-review .fp-review-empty { color:var(--text-muted); padding:14px; background:var(--subtle-fg); border-radius:6px; }
      .fp-review li + li { margin-top:6px; }
      .fp-review .fp-review-card,.fp-review .fp-review-field { min-width:0; overflow-wrap:anywhere; }
      @media (max-width:600px) { .fp-review .fp-review-card { padding:14px; } .fp-review .fp-review-section-heading { flex-wrap:wrap; } }
      .fp-review dd { margin:0 0 10px; }
    </style>`;
    wrapper.html(`<p class="text-muted">${__("Loading scout submission…")}</p>`);
    let data;
    try {
      ({message: data} = await frappe.call("fieldpulse.scout_submissions.submission_detail", {response: frm.doc.name}));
    } catch {
      wrapper.html(`<p class="text-danger">${__("Unable to load the submission. Refresh to try again.")}</p>`);
      return;
    }
    if (data.brief) {
      const pinned = data.brief, submitted = data.submission || {};
      const checks = pinned.brief.checks.filter(check => pinned.check_ids.includes(check.id));
      const evidence = data.evidence || [];
      const completion = data.completion || {};
      const summaries = new Map((completion.checks || []).map(check => [check.id, check]));
      const arrival = submitted.arrival || {};
      const flags = [...(completion.errors || []), ...(completion.flags || [])];
      const evidenceCard = e => `<article class="fp-review-evidence">
        <div class="fp-review-evidence-heading"><strong>${esc(e.evidence_type || "Evidence")}</strong>${badge("Uploaded")}</div>
        ${text(e.caption || "No caption provided")}
        ${block("Captured at", e.captured_at || "Not recorded")}
        <details><summary>Capture details</summary>${block("GPS coordinates", e.gps_lat != null && e.gps_lng != null ? `${e.gps_lat}, ${e.gps_lng}` : "Not recorded")}${block("GPS accuracy", e.accuracy_m != null ? `${e.accuracy_m} m` : "Not recorded")}${e.description ? block("Description", e.description) : ""}</details>
        <button type="button" class="btn btn-default btn-sm" data-evidence="${esc(e.name)}">Open ${esc(e.evidence_type || "evidence")}</button>
      </article>`;
      const responses = checks.map((check, index) => {
        const answer = submitted.answers?.[check.id];
        const summary = summaries.get(check.id);
        const media = evidence.filter(e => e.field_check_id === check.id);
        const unable = answer?.status === "unable_to_verify";
        const label = unable ? "Unable to verify" : !answer ? "No response" : summary?.missing?.length ? "Needs attention" : "Recorded";
        const requirements = (check.evidence || []).map(rule => `<li><strong>${esc(rule.minimum)} ${esc(rule.kind)} capture(s)</strong>${rule.instruction ? ` &mdash; ${esc(rule.instruction)}` : ""}</li>`).join("");
        return card(`${index + 1}. ${check.instruction}`,
          `<div class="fp-review-meta">${check.required ? "Required check" : "Optional check"}</div>` +
          (summary?.missing?.length ? `<div class="fp-review-notice">${block("Needs attention", summary.missing)}</div>` : "") +
          `<div class="fp-review-answer">${block(unable ? "Why this could not be verified" : "Scout response", unable ? answer.explanation : answer?.value ?? "No response recorded")}${!unable && answer?.explanation ? block("Explanation", answer.explanation) : ""}</div>` +
          `<div class="fp-review-evidence-section"><h5>Supporting evidence (${media.length})</h5>${requirements ? `<details><summary>Evidence requirements</summary><ul>${requirements}</ul></details>` : ""}${media.length ? `<div class="fp-review-grid">${media.map(evidenceCard).join("")}</div>` : `<div class="fp-review-empty">No uploaded evidence linked to this check.</div>`}</div>`,
          badge(label, unable || !answer || summary?.missing?.length ? "warning" : "neutral"));
      }).join("");
      wrapper.html(styles + `<div class="fp-review">` +
        card("Submission review", `<div class="fp-review-grid fp-review-overview">${block("Assigned checks", checks.length)}${block("Uploaded evidence", evidence.length)}${block("Submitted", frm.doc.submitted_at || "Not recorded")}</div>` +
          text("Review the scout's findings and supporting evidence before recording a decision.") +
          (flags.length ? `<div class="fp-review-notice">${block("Review flags and limitations", flags)}</div>` : "") +
          (frm.doc.review_notes ? block("Coordinator notes", frm.doc.review_notes) : ""), badge(frm.doc.qa_status || "Pending")) +
        card(pinned.brief.title || "Approved Task Brief", block("Objective", pinned.brief.objective) +
          `<details><summary>Scope and assigned instructions</summary>${block("Scope", pinned.brief.scope)}${block("Instructions", pinned.brief.instructions)}</details>`) +
        card("Arrival", `<div class="fp-review-grid">${block("Distance from site", frm.doc.geofence_distance_m != null ? `${frm.doc.geofence_distance_m} m` : "Not recorded")}${block("GPS accuracy", arrival.accuracy_m != null ? `${arrival.accuracy_m} m` : "Not recorded")}${block("Captured at", arrival.captured_at || "Not recorded")}</div><details><summary>Arrival coordinates</summary>${text(arrival.latitude != null && arrival.longitude != null ? `${arrival.latitude}, ${arrival.longitude}` : "Not recorded")}</details>`, badge(frm.doc.geofence_status || "Not recorded")) +
        (submitted.access_issue ? card("Access issue", structured(submitted.access_issue), badge("Needs review", "warning")) : "") +
        `<div class="fp-review-section-heading"><h4>Scout findings</h4><span class="fp-review-meta">${checks.length} assigned checks</span></div>` + responses +
        card("Additional observations", text(submitted.additional_observations || "No additional observations.")) +
        card("Submission checks", text("Technical completeness does not verify the findings or evidence.") + block("Scout declaration", submitted.declaration === true ? "Confirmed" : "Not confirmed") +
          `<details><summary>Technical completeness details</summary>${structured(completion)}</details>`, badge(completion.complete === true ? "Technically complete" : "Incomplete", completion.complete === true ? "neutral" : "warning")) + `</div>`);
      wrapper.find('[data-evidence]').on('click',async function(){
        const {message}=await frappe.call('fieldpulse.evidence.get_evidence_view_url',{evidence_id:this.dataset.evidence});
        window.open(message.view_url,'_blank','noopener,noreferrer');
      });
      if(frm.doc.status==='Submitted'&&!['Passed','Failed'].includes(frm.doc.qa_status)){
        const actions=[
          {decision:'Approve',label:'Approve'},
          {decision:'Reject',label:'Reject'},
          {decision:'Request clarification',label:'Request clarification and resubmission'},
        ];
        for(const action of actions)frm.add_custom_button(__(action.label),()=>{
          const askForReason=()=>frappe.prompt(
          [{fieldname:'notes',fieldtype:'Small Text',label:action.decision==='Reject'?__('Rejection reason'):__('Review findings and instructions'),reqd:1}],async values=>{
            await frappe.call({method:'fieldpulse.task_brief_workflow.review_response',args:{response:frm.doc.name,decision:action.decision,notes:values.notes},freeze:true});
            await frm.reload_doc();
            if(action.decision==='Reject')frappe.msgprint(__('This assignment is rejected and closed. The project is now Awaiting Assignment. This scout cannot be assigned to this project again.'));
            if(action.decision==='Request clarification')frappe.msgprint(__('A full resubmission was sent to the scout. They can update answers and add new evidence using the camera or gallery.'));
          },__(action.label),__('Record decision'));
          if(action.decision==='Reject')frappe.confirm(__('Rejecting closes this scout\'s assignment and returns the project to Awaiting Assignment. This scout will not be eligible for this project again. The project can be assigned to another scout. Continue?'),askForReason);
          else askForReason();
        });
      }
      return;
    }
    const request = data.client_request || {};
    const arrival = data.arrival || {};
    const final = data.final_review || {};
    const answers = new Map((data.answers || []).map(a => [a.question, a]));
    const summaries = new Map((data.summary || []).map(s => [s.code, s]));
    const renderAnswer = (answer, question) => {
      if (!answer) return text("No answer recorded");
      const value = parse(answer.answer_json, null);
      if (!value || typeof value !== "object" || Array.isArray(value)) return structured(answer.answer_text || value || "No answer recorded");
      const rules = parse(question.validation_json);
      const labels = Object.fromEntries((rules.items || []).map(item => [item.id, item.label]));
      return (value.blocked ? badge("Unable to check", "warning") : "") +
        [
          ["Result", value.result], ["Results", value.results], ["Scout response", value.text],
          ["Finding basis", value.source_type], ["Confirming office / role", value.source_role], ["Uses explanation from", value.explanation_ref],
          ...Object.entries(value.blocked ? {} : value.items || {}).map(([id, item]) => [labels[id] || humanize(id), item]),
          ...Object.entries(value.exceptions || {}).map(([id, exception]) => ["Evidence unavailable · " + (labels[id] || humanize(id)), exception]),
          ["Explanation / follow-up", value.explanation], ["Source and statement", value.source],
          ["Concern and location", value.concern_details], ["Evidence limitation", value.media_unavailable_reason],
          ["Demonstration", value.demonstration],
        ].filter(([, value]) => value != null && value !== "").map(([label, value]) => block(label, value)).join("");
    };
    const seen = new Set();
    const context = [
      ["Full client request", request.client_request || request.task_scope], ["Agreed scope", request.agreed_scope],
      ["Assigned checks", request.task_scope], ["Request-specific evidence tasks", request.evidence_tasks],
    ].filter(([, value]) => {
      const key = JSON.stringify(value);
      if (!value || seen.has(key)) return false;
      seen.add(key); return true;
    }).map(([label, value]) => block(label, value)).join("");
    const evidenceCard = e => `<div class="fp-review-evidence"><div class="fp-review-evidence-heading"><strong>${esc(e.evidence_type || "Evidence")}</strong>${badge(e.evidence_type === "Document" ? "Imported document" : e.location_check?.status || "Unverified")}</div>${text(e.caption || "No caption")}${e.description ? block("Subject detail", e.description) : ""}${e.metadata_origin ? block("Evidence origin", e.metadata_origin) : ""}${e.location_sampled_at ? block("GPS sampled at", e.location_sampled_at) : ""}${e.requirement_id ? block("Evidence requirement", e.requirement_id) : ""}${e.support_note ? block("Support note", e.support_note) : ""}<div class="fp-review-meta">${esc(e.captured_at || "Capture time unavailable")} · GPS accuracy: ${esc(e.accuracy_m ?? "Unknown")} m</div><details><summary>Capture location</summary>${text(e.gps_lat != null && e.gps_lng != null ? `${e.gps_lat}, ${e.gps_lng}` : "GPS unavailable")}</details><button type="button" class="btn btn-default btn-sm" data-evidence="${esc(e.name)}">Open ${esc(e.evidence_type || "evidence")}</button></div>`;
    const questions = (final.visit_route === "arrival_exception" ? [] : data.questions || []).map((q, index) => {
      const answer = answers.get(q.name);
      if (q.question_code === "S_EXTRA" && !answer) return "";
      const summary = summaries.get(q.question_code);
      const media = (data.evidence || []).filter(e => answer && e.question_response === answer.name);
      const status = summary?.skipped ? badge("Skipped by visit outcome") : !answer ? badge("Unanswered", "warning") : summary?.errors?.length || summary?.reasons?.length ? badge("Needs attention", "warning") : badge("Recorded", "success");
      const checks = summary ? [...(summary.errors || []), ...(summary.reasons || [])] : [];
      const requirements = (summary?.evidence || []).map(e => `<li><strong>${esc(e.kind)}</strong> · ${esc(e.state)} · ${esc(e.subject)}</li>`).join("");
      return card(`${index + 1}. ${q.label || q.question_code}`, `<div class="fp-review-meta">${esc(q.question_code)}</div>${checks.length ? `<div class="fp-review-notice">${block("Review flags", checks)}</div>` : ""}${q.help_text ? block("Assigned instructions", q.help_text) : ""}${renderAnswer(answer, q)}${requirements ? `<details><summary>Evidence checks</summary><ul>${requirements}</ul></details>` : ""}<div class="fp-review-evidence-section"><h5>Supporting evidence <span class="text-muted">(${media.length})</span></h5>${media.length ? `<div class="fp-review-grid">${media.map(evidenceCard).join("")}</div>` : text("No uploaded evidence linked to this answer.")}</div>`, status);
    }).join("");
    wrapper.html(styles + `<div class="fp-review">` +
      card("Submission review", block("Outcome", data.review_status || "Awaiting review") + (data.review_reasons ? `<div class="fp-review-notice">${block("Limitations and review reasons", data.review_reasons)}</div>` : "") + (frm.doc.review_notes ? block("Coordinator notes", frm.doc.review_notes) : ""), badge(frm.doc.qa_status || "Pending")) +
      (context ? card("Client request and agreed scope", context + (request.clarifications || []).map(c => block(c.question, c.answer)).join("")) : "") +
      card("Arrival verification", `<div class="fp-review-grid">${block("Distance from site", arrival.distance_m != null ? `${arrival.distance_m} m` : "Unknown")}${block("GPS accuracy", arrival.accuracy_m != null ? `${arrival.accuracy_m} m` : "Unknown")}${block("Captured at", arrival.captured_at || "Unknown")}</div>${arrival.exception_reason ? `<div class="fp-review-notice">${block("Arrival exception", arrival.exception_reason)}</div>` : ""}`, badge(arrival.status || "Not recorded", arrival.status === "Inside" ? "success" : "warning")) +
      `<h4 style="margin:24px 0 14px">Scout responses</h4>` + (questions || text("No questionnaire responses available.")) +
      (final.visit_route === "arrival_exception"
        ? card("Arrival issue", block("Reason", final.arrival_exception_reason) + text("The questionnaire remained locked. No verified arrival or completed fieldwork is recorded."), badge("Needs review", "warning"))
        : card("Final request coverage", block("Coverage", final.coverage) + block("Additional observations or answers", final.additional_text || "Nothing further added") + (final.capture_location_explanation ? block("Capture location explanation", final.capture_location_explanation) : "") + (final.incomplete ? `<div class="fp-review-notice">${block("Incomplete visit reason", final.incomplete_reason)}</div>` : ""))) + `</div>`);
    wrapper.find("[data-evidence]").on("click", async function () {
      const {message} = await frappe.call("fieldpulse.evidence.get_evidence_view_url", {evidence_id: this.dataset.evidence});
      window.open(message.view_url, "_blank", "noopener,noreferrer");
    });
    frm.set_intro(__('Historical questionnaire submission: read-only audit record. New work uses Task Briefs.'));
  }
});
