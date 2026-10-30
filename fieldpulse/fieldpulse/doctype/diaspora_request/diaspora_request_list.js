if (frappe.boot.dd_native_handover_active) {
  frappe.listview_settings["Diaspora Request"] = {
    ...frappe.listview_settings["Diaspora Request"],
    get_indicator: () => null,
    onload(listview) {
      if (listview.dd_submission_column_hidden) return;
      listview.dd_submission_column_hidden = true;
      const setup = listview.setup_columns.bind(listview);
      listview.setup_columns = () => {
        setup();
        listview.columns = listview.columns.filter(column => column.df?.fieldname !== "submission_id");
      };
      listview.setup_columns();
      listview.render_header(true);
    },
  };
}
