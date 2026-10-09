frappe.ui.form.on("Diaspora Request", {
  refresh(frm) {
    if (frm.is_new() || !frm.perm.some(p => p.write)) return;
    frm.set_df_property("status", "description", __("Assign scouts through the project's Field Request. Changing status alone does not assign a scout."));
    frm.add_custom_button(__("Assign scouts"), async () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__("Save this request before assigning scouts."));
        return;
      }
      const projects = await frappe.db.get_list("Field Request", {
        filters: { diaspora_request: frm.doc.name },
        fields: ["name"], limit: 100,
      });
      if (!projects.length) {
        frappe.msgprint(__("Create and save a Field Request linked to this request to prepare its projects, then use Assign scouts on the project."));
        frappe.new_doc("Field Request", { source: "Diaspora Desk", diaspora_request: frm.doc.name, source_reference: frm.doc.name });
        return;
      }
      if (projects.length === 1) {
        frappe.set_route("Form", "Field Request", projects[0].name);
        return;
      }
      const dialog = new frappe.ui.Dialog({
        title: __("Choose the project to assign"),
        fields: [{ fieldname: "project", label: __("Field Request"), fieldtype: "Link", options: "Field Request", reqd: 1,
          get_query: () => ({ filters: { diaspora_request: frm.doc.name } }) }],
        primary_action_label: __("Open project"),
        primary_action(values) {
          dialog.hide();
          frappe.set_route("Form", "Field Request", values.project);
        },
      });
      dialog.show();
    });
  },
});
