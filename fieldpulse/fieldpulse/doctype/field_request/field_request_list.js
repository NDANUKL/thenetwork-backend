frappe.listview_settings["Field Request"] = {
  add_fields: ["project_title"],
  // Subject formatters return text: Frappe creates the anchor itself.
  formatters: { name: value => value || "" },
  onload(listview) {
    if (listview.dd_request_subject) return;
    listview.dd_request_subject = true;
    const subject = listview.get_subject_element.bind(listview);
    listview.get_subject_element = (doc) => {
      const element = subject(doc, doc.name);
      const link = element.querySelector("a");
      if (link) {
        link.textContent = doc.name;
        link.setAttribute("title", doc.project_title || doc.name);
      }
      return element;
    };
  },
};
