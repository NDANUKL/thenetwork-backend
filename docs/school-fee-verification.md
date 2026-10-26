# School fee payment verification

School fee payment checks are available for students of all ages. Confirm authorised institutional payment records only; the exception does not include student contact, observation, attendance, enrollment, welfare or medical checks.

The stable internal code remains `university_fees` for historical links. The displayed service is School fee payment confirmation. New fee questionnaires use version 4 for legacy protocol, 5 for protocol 2, and 6 for visit workflow. Historical catalogue files, published questionnaires and existing project/task pins remain unchanged. Other service questionnaires retain their original versions.

The FP Questionnaire list hides the old university title by default. The FP Question list also excludes the historical shared fee templates `DD-university_fees-v1`, `DD-university_fees-v2` and `DD-university_fees-v3` by default, leaving the school fee questions visible. Remove the list filter to inspect historical questions. These display filters do not delete or deactivate questions or change existing assignments.

Deploy the native backend and run the normal migration/template installation (`fieldpulse.scout_templates.install_templates`, invoked by the existing migration hook). Enable no new workflow flags for this change. Verify a primary-school fee request and a payment receipt request select the fee service, confirm coordinator authorisation and payment fields, and verify existing assignments retain their pinned questionnaires. No disabled legacy scripts need to be modified or re-enabled.
