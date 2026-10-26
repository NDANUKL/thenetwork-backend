frappe.ui.form.on("Scout Profile", {
  refresh(frm) {
    const reviewer = frappe.session.user === "Administrator" ||
      ["System Manager", "Admin", "Field Operations Coordinator"].some(role => frappe.user_roles.includes(role));
    if (!frm.is_new() && reviewer && frm.doc.user && frm.doc.access_status !== "Deactivated") {
      frm.add_custom_button(__("Deactivate"), () => frappe.prompt(
        { fieldname: "reason", fieldtype: "Small Text", label: __("Reason for deactivation"), reqd: 1,
          description: __("Blocks sign-in and revokes sessions. Existing tasks and records are retained; review outstanding assignments.") },
        values => frappe.call({
          method: "fieldpulse.scout_access.deactivate_scout",
          args: { scout_profile: frm.doc.name, reason: values.reason }, freeze: true,
          callback: () => frm.reload_doc(),
        }), __("Deactivate scout access"), __("Deactivate")
      ));
    }
    if (frm.doc.access_status === "Deactivated") {
      frm.set_intro(__("Scout access is deactivated. Sign-in and new assignments are blocked."), "red");
    }
    if (frappe.session.user === "Administrator" || !frappe.user_roles.includes("Field Operations Coordinator")) return;
    frm.fields.forEach(field => frm.set_df_property(field.df.fieldname, "read_only", 1));
    frm.disable_save();
    if (frm.doc.access_status !== "Deactivated") frm.set_intro(__("Scouts maintain their profile and leave settings in the mobile app."), "blue");
  },
});
