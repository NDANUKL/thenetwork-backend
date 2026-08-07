app_name = "fieldpulse"
app_title = "FieldPulse"
app_publisher = "FieldPulse Team"
app_description = "Offline-first geo-coded task platform for field agents"
app_email = "admin@example.com"
app_license = "MIT"

fixtures = [
    {"dt": "Role", "filters": [["role_name", "in", ["Field Agent", "Supervisor", "Admin"]]]}
]

after_install = "fieldpulse.install.after_install"
