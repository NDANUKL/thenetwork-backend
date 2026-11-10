// Only prospective planning dates: accounting and historical dates remain available.
(() => {
  const fields = {
    'DD Quotation': ['valid_until'],
    'DD Scout Offer': ['valid_until'],
    'Diaspora Request': ['deadline_date'],
    'Field Request': ['deadline'],
  };
  for (const [doctype, names] of Object.entries(fields)) {
    const handlers = {
      refresh(frm) {
        for (const name of names) {
          const control = frm.fields_dict[name];
          if (!control) continue;
          const minimum = frappe.datetime.str_to_obj(frappe.datetime.get_today());
          // Avoid refreshing/reformatting the control during date selection.
          control.df.min_date = minimum;
          if (control.datepicker) {
            control.$input.off('focus.planning_dates');
            control.datepicker.update({ minDate: minimum });
          }
        }
      },
      validate(frm) {
        for (const name of names) {
          const control = frm.fields_dict[name];
          if (control && !control.df.read_only && frm.doc[name] && frm.doc[name] < frappe.datetime.get_today()) {
            // Existing elapsed plans can still be maintained; changing dates cannot backdate them.
            if (!frm.is_new() && frm.doc[name] === frm._planning_original_dates?.[name]) continue;
            frappe.throw(__('{0} must be today or later.', [__(control.df.label)]));
          }
        }
      },
      onload(frm) {
        frm._planning_original_dates = Object.fromEntries(names.map(name => [name, frm.doc[name]]));
      },
    };
    frappe.ui.form.on(doctype, handlers);
  }
})();
