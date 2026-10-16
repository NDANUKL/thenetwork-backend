# Production and backend alignment

Production remains controlled by the existing site Server Scripts and Client Scripts until the owner explicitly approves a native-backend handover. Preserve their behavior and active states. Do not disable, delete, or replace a working production script merely because matching native source exists locally. Do not run automatic adoption/retirement migrations against production now.

For every production change, back up the targeted definitions, make and verify the script change, and mirror its definitions and behavior into `Documents/thenetwork-backend`. The local native checkout is not evidence of deployment. Temporary scripts can be retired only during an explicitly approved backend deployment, after parity and rollback checks.

Confirmed policy: one quotation with 50% deposit and 50% balance; assign scouts only after verified deposit. Customers may review the complete approved report before paying the balance. Responsibility and Location columns stay removed from the assignment dialog. Existing recorded destinations and task metadata remain available to operational code.
