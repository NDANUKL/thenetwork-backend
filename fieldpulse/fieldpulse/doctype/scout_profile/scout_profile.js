frappe.ui.form.on("Scout Profile", {
  refresh(frm) {
    if (frappe.session.user === "Administrator" || !frappe.user_roles.includes("Field Operations Coordinator")) return;
    frm.fields.forEach(field => frm.set_df_property(field.df.fieldname, "read_only", 1));
    frm.disable_save();
    frm.set_intro(__("Scouts maintain their profile and leave settings in the mobile app."), "blue");
  },
});
