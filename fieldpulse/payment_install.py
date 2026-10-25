"""Native payment schemas are installed by Frappe model sync."""

def after_migrate():
    from fieldpulse.alignment_install import sync_dashboard
    sync_dashboard()
    install()


def install():
    from fieldpulse.finance_install import install as install_finance_role
    install_finance_role()
    # All payment fields, permissions and print format are versioned Frappe documents.
    # Retirement belongs exclusively to the explicitly approved native handover.
    from fieldpulse.scout_templates import install_templates
    install_templates()
