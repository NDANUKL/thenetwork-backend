frappe.listview_settings["DD Customer Notification"] = {
  onload(listview) {
    if (!frappe.user.has_role("System Manager")) return;

    const method = "fieldpulse.customer_notifications.";
    listview.page.add_inner_button(__("Preview beta reminder"), async () => {
      const { message: preview } = await frappe.call({
        method: method + "preview_beta_reminder",
        type: "POST",
        freeze: true,
        freeze_message: __("Checking eligible clients..."),
      });

      if (!preview.ready) {
        frappe.msgprint(__("No clients are eligible for a new reminder."));
        return;
      }

      const dialog = new frappe.ui.Dialog({
        title: __("Send beta reminder"),
        fields: [{ fieldtype: "HTML", fieldname: "summary" }],
        primary_action_label: __("Send reminder"),
        async primary_action() {
          dialog.get_primary_btn().prop("disabled", true);
          try {
            const { message: result } = await frappe.call({
              method: method + "send_beta_reminder",
              type: "POST",
              args: { before: preview.before },
              freeze: true,
              freeze_message: __("Queueing beta reminders..."),
            });
            dialog.hide();
            frappe.msgprint(result.ready
              ? __("Reminders queued for {0} client(s). Check this list for delivery status.", [result.ready])
              : __("No new reminders were queued."));
            listview.refresh();
          } finally {
            dialog.get_primary_btn().prop("disabled", false);
          }
        },
      });

      dialog.fields_dict.summary.$wrapper.text(
        __("{0} client(s) are eligible. Send them the Diaspora Desk beta reminder?", [preview.ready])
      );
      dialog.show();
    });
  },
};
