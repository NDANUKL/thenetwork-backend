# Production workflow

Production native handover completed on 16 October 2026 and was verified against the live site on 26 October 2026. Runtime changes belong in this repository's native Python modules, standard DocTypes and Desk assets. The retired DD Server Scripts and Client Scripts remain disabled recovery references; do not delete, re-enable or update them as runtime owners. Do not rerun handover/retirement migrations merely because source changes. Preserve the simplified scout assignment dialog without Responsibility and Location inputs. Read docs/production-script-ownership.md and docs/native-integration.md before changing integrations.

## Native integration source

Read docs/native-integration.md and fieldpulse/configuration/native-ownership.json before changing Frappe behavior. The ownership registry and dated production snapshot retain the historical script audit; they do not make retired scripts authoritative. Do not recreate the website's removed script installers or run old website mirror generators over native source. Source changes still require normal deployment and verification; local changes are not proof of production deployment.

## Documentation authority

`docs/production-script-ownership.md` is the controlling cross-repository production policy; `docs/production-handover-verification-2026-10-26.md` records the live evidence. Website/mobile guides must link to that policy rather than maintain a competing ownership procedure. `DiasporaDesk/backend-review` is a historical review snapshot, not an active backend checkout or deployment guide. When runtime ownership changes, update the controlling policy and the referring agent/setup guides in the same change. Clearly distinguish dated audits, current source behavior and verified deployed feature state.
