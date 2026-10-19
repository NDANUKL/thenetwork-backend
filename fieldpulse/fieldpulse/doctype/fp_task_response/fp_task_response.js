frappe.ui.form.on("FP Task Response", {
  async refresh(frm) {
    if (frm.is_new() || !["Field Operations Coordinator", "System Manager"].some(r => frappe.user.has_role(r))) return;
    const escape = frappe.utils.escape_html;
    const { message: data } = await frappe.call("fieldpulse.scout_submissions.submission_detail", {response: frm.doc.name});
    const block = (title, value) => `<section style="margin:20px 0"><h4>${escape(title)}</h4><p style="white-space:pre-wrap">${escape(String(value ?? "Not recorded"))}</p></section>`;
    const request = data.client_request || {};
    const arrival = data.arrival || {};
    const final = data.final_review || {};
    const renderAnswer = answer => {
      if (!answer) return "No answer";
      let value;
      try { value = JSON.parse(answer.answer_json || "null"); } catch { value = null; }
      if (!value || typeof value !== "object" || Array.isArray(value)) return answer.answer_text || String(value ?? "No answer");
      return [value.result, value.text, value.explanation && "Explanation / follow-up: " + value.explanation,
        value.source && "Source and statement: " + value.source, value.concern_details && "Concern and location: " + value.concern_details,
        value.media_unavailable_reason && "Evidence limitation: " + value.media_unavailable_reason,
        value.demonstration && "Demonstration: " + value.demonstration].filter(Boolean).join("\n\n");
    };
    const answers = new Map(data.answers.map(a => [a.question, a]));
    const html = block("Full client request", request.client_request || request.task_scope) + block("Agreed scope", request.agreed_scope || request.task_scope) +
      block("This taskâ€™s assigned checks", request.task_scope) + block("Request-specific evidence tasks", request.evidence_tasks) +
      (request.clarifications || []).map(c => block(c.question, c.answer)).join("") +
      block("Arrival check", `${arrival.status || "Not recorded"}\nDistance: ${arrival.distance_m ?? "Unknown"} m\nGPS accuracy: ${arrival.accuracy_m ?? "Unknown"} m\nCaptured: ${arrival.captured_at || "Unknown"}\nException: ${arrival.exception_reason || "None"}`) +
      block("Review status", [data.review_status, data.review_reasons].filter(Boolean).join("\n")) +
      data.questions.map(q => {
        const answer = answers.get(q.name);
        if (q.question_code === "S_EXTRA" && !answer) return "";
        const media = data.evidence.filter(e => e.question_response === answer?.name);
        return block(q.question_code + " - " + q.label, renderAnswer(answer)) +
          media.map(e => `<p><button type="button" class="btn btn-default btn-xs" data-evidence="${escape(e.name)}">View ${escape(e.evidence_type)}</button> ${escape(e.caption || "No caption")} <small>${escape(e.captured_at || "")} ${escape(e.location_check?.status || "Unverified")} / accuracy ${escape(String(e.accuracy_m ?? "Unknown"))} m ${escape(e.gps_lat != null && e.gps_lng != null ? `GPS ${e.gps_lat}, ${e.gps_lng}` : "GPS unavailable")}</small></p>`).join("");
      }).join("") + block("Final request coverage", final.coverage) + block("Additional observations or answers", final.additional_text || "Nothing further added") +
      (final.incomplete ? block("Incomplete visit reason", final.incomplete_reason) : "");
    frm.fields_dict.submission_review.$wrapper.html(html).find("[data-evidence]").on("click", async function () {
      const {message} = await frappe.call("fieldpulse.evidence.get_evidence_view_url", {evidence_id: this.dataset.evidence});
      window.open(message.view_url, "_blank", "noopener,noreferrer");
    });
    if (frm.doc.status !== "Submitted" || ["Passed", "Failed"].includes(frm.doc.qa_status)) return;
    for (const decision of ["Approve", "Request rework"]) {
      frm.add_custom_button(__(decision), () => frappe.prompt([
        {fieldname: "notes", label: __("Review against the complete client request, evidence and limitations"), fieldtype: "Small Text", reqd: 1}
      ], async ({notes}) => {
        await frappe.call("fieldpulse.scout_submissions.review_submission", {response: frm.doc.name, decision, notes});
        frm.reload_doc();
      }, __(decision)));
    }
  }
});
