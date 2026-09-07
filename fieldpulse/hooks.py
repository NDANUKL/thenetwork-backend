app_name = "fieldpulse"
app_title = "FieldPulse"
app_publisher = "FieldPulse Team"
app_description = "Offline-first geo-coded task platform for field agents"
app_email = "admin@example.com"
app_license = "MIT"

fixtures = [
    {
        "dt": "Role",
        "filters": [[
            "role_name",
            "in",
            [
                "Field Agent",
                "Supervisor",
                "Admin",
                "Diaspora Website Integration",
                "Field Operations Coordinator",
            ],
        ]],
    }
]

after_install = "fieldpulse.install.after_install"

doc_events = {
    "Diaspora Request": {
        "after_insert": "fieldpulse.integrations.diaspora_request.create_field_request",
    },
}

