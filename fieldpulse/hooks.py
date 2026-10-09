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
        "before_save": "fieldpulse.project_alignment.map_diaspora",
        "after_insert": "fieldpulse.integrations.diaspora_request.create_field_request",
    },
    "Field Request": {
        "before_save": "fieldpulse.project_alignment.map_field_request",
        "on_update": "fieldpulse.project_alignment.expand_projects",
    },
    "Field Task": {"before_save": "fieldpulse.project_alignment.map_task"},
}

after_migrate = "fieldpulse.alignment_install.sync_dashboard"

scheduler_events = {
    "daily": [
        "fieldpulse.fieldpulse.doctype.scout_profile.scout_profile.refresh_activity_statuses",
    ],
}


# Preserve callers of the former site Server Script API.
override_whitelisted_methods = {
    "dd_assign_project_scouts": "fieldpulse.project_alignment.assign_project_scouts",
}
