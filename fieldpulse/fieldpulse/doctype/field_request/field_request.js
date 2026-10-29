if (frappe.boot.dd_native_handover_active) {
// DD Alignment Project Form
frappe.ui.form.on("Field Request", {
  refresh(frm) {
    if (!frm.is_new()) frm.add_custom_button(__("County assignment balance"), () => frappe.set_route("query-report", "County Assignment Balance", {field_request: frm.doc.name}));
    frm.set_df_property("source", "read_only", 1);
    frm.set_df_property("diaspora_request", "hidden", !frm.doc.diaspora_request);
    if (!frm.doc.diaspora_request) {
      if (frm.doc.source !== "Manual") frm.set_value("source", "Manual");
      return;
    }
    ["source", "source_reference", "diaspora_request", "request_type", "county", "field_brief", "project_number", "project_title", "project_key", "evidence_requirements", "customer_target_date", "deadline_preference", "status"].forEach(field => frm.set_df_property(field, "read_only", 1));
    frm.set_df_property("source_reference", "hidden", 1);
    frm.set_df_property("dd_site_locations", "hidden", 1);
    frm.set_df_property("deadline", "label", "Agreed work deadline");
    frm.set_df_property("deadline", "description", "Copied to the scout task's Due date. Confirm this date when arranging the work.");
    const missing = [];
    if (!frm.doc.county) missing.push("Add the project county.");
    if (!frm.doc.approved_task_brief) missing.push("Review and approve this project's Task Brief before assigning a scout.");
    frm.set_intro(missing.join(" "), "orange");
  },
});


// DD Project Scout Assignment
frappe.ui.form.on("Field Request", {
  refresh(frm) {
    frm.remove_custom_button(__("Assign scouts"));
    frm.set_df_property("priority", "description", "");
    frm.set_df_property("deadline", "description", "");
    frm.set_df_property("status", "description", __("Use Assign scouts to select a Scout Profile and create their Field Task. Changing status alone does not assign a scout."));

    if (frm.is_new() || ["Completed", "Cancelled"].includes(frm.doc.status) || !frm.perm.some(p => p.write)) return;
    frm.add_custom_button(__("Assign scouts"), async () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__("Save this project before assigning scouts."));
        return;
      }
      if ((frm.doc.diaspora_request && !frm.doc.project_number) || frm.doc.alignment_review || !frm.doc.county) {
        frappe.msgprint(__("Confirm this project's scope, project number and county before assigning scouts."));
        return;
      }
      if (!frm.doc.approved_task_brief) {frappe.msgprint(__('Approve a Task Brief first.')); return;}
      const brief = await frappe.db.get_doc('DD Task Brief', frm.doc.approved_task_brief);
      const checks = JSON.parse(brief.content_json).checks;
      const dialog = new frappe.ui.Dialog({
        title: __("Assign scouts to this project"),
        fields: [{ fieldname: "assignment_help", fieldtype: "HTML", options: `<p>${__("Choose a scout in each row. Every new row starts with all field checks. Use Choose checks to give a scout a smaller set.")}</p>` },
          { fieldname: "assignments", label: __("Scout assignments"), fieldtype: "Table", reqd: 1, in_place_edit: true, data: [{check_ids: checks.map(check => check.id).join(", "),check_labels:checks.map(check=>check.instruction).join('; ')}],
          fields: [
            { fieldname: "scout", label: __("Scout"), fieldtype: "Link", options: "Scout Profile", reqd: 1, in_list_view: 1,
              get_query: () => ({ filters: { access_status: ["!=", "Deactivated"] } }),
              async onchange() {
                const row = this.doc;
                if (!row) return;
                const selected = row.scout;
                row.scout_name = "";
                row.base_county = "";
                dialog.fields_dict.assignments.grid.refresh();
                if (!selected) return;
                const result = await frappe.db.get_value("Scout Profile", selected, ["scout_name", "base_county"]);
                if (row.scout !== selected) return;
                row.scout_name = result.message?.scout_name || "";
                row.base_county = result.message?.base_county || __("County unconfirmed");
                dialog.fields_dict.assignments.grid.refresh();
              },
            },
            { fieldname: "scout_name", label: __("Full name"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
            { fieldname: "base_county", label: __("County"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
            {fieldname:'check_ids',fieldtype:'Small Text',hidden:1,default:checks.map(check=>check.id).join(', ')},
            {fieldname:'check_labels',label:__('Assigned checks'),fieldtype:'Small Text',read_only:1,in_list_view:1,default:checks.map(check=>check.instruction).join('; ')},
            {fieldname:'select_checks',label:__('Choose checks'),fieldtype:'Button',in_list_view:1,click(){
              const row=this.doc;
              if(!row)return;
              const selected=new Set((row.check_ids||'').split(',').map(id=>id.trim()));
              frappe.prompt([{fieldname:'checks',label:__('Checks for this scout'),fieldtype:'MultiCheck',reqd:1,sort_options:false,
                options:checks.map(check=>({label:frappe.utils.escape_html(check.instruction),value:check.id,checked:selected.has(check.id)}))}],values=>{
                  row.check_ids=values.checks.join(', ');
                  row.check_labels=checks.filter(check=>values.checks.includes(check.id)).map(check=>check.instruction).join('; ');
                  dialog.fields_dict.assignments.grid.refresh();
                },__('Choose checks'),__('Apply'));
            }},
          ] }],
        primary_action_label: __("Assign"),
        async primary_action(values) {
          const emptyRow = values.assignments.findIndex(row => !(row.check_ids || '').split(',').some(id => id.trim()));
          if (emptyRow !== -1) {
            frappe.msgprint(__('Row {0}: use Choose checks to select at least one field check for this scout.', [emptyRow + 1]));
            return;
          }
          dialog.disable_primary_action();
          try {
            const result = await frappe.call({ method: "dd_assign_scouts_without_extra_columns", args: { field_request: frm.doc.name, assignments: JSON.stringify(values.assignments.map(row => ({...row,check_ids:(row.check_ids || "").split(",").map(id => id.trim()).filter(Boolean)}))) }, freeze: true });
            dialog.hide();
            const assigned = await frappe.db.get_list("Field Task", {filters: {name: ["in", result.message.tasks]}, fields: ["name", "task_number"], limit: 20});
            frappe.msgprint(__("Scout tasks: {0}", [assigned.map(task => task.task_number || task.name).join(", ")]));
            await frm.reload_doc();
          } finally { dialog.enable_primary_action(); }
        },
      });
      dialog.show();
    });
  },
});


}

frappe.ui.form.on('Field Request', {
  refresh(frm) {
    frm.set_query('approved_task_brief', () => ({filters:{project:frm.doc.name,status:'Approved'}}));
    if (frm.is_new()) return;
    frm.add_custom_button(__('Task Briefs'), () => frappe.set_route('List','DD Task Brief',{project:frm.doc.name}));
    frm.add_custom_button(__('Open Task Brief'), async () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__('Save this project before opening its Task Brief.'));
        return;
      }
      const result = await frappe.call({method:'fieldpulse.task_brief_workflow.open_project_brief',
        args:{project:frm.doc.name},freeze:true});
      frappe.set_route('Form','DD Task Brief',result.message);
    });
  }
});
