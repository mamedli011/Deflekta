# sandbox/ (Role 3)
Task list: `tasks/R3_sandbox.md`. Interface: `execute(tool, args) -> ToolResult`, `TOOL_DECLARATIONS`.
- send_email, http_request, delete_file only return "logged". No SMTP, no outbound POST, no file deletion. Ever.
- read_file stays confined to `sandbox/fakefs/`.
- browse_web only fetches hosts in `ALLOWED_BROWSE_HOSTS`.
- Every evil page goes into `pages/manifest.json` with its technique. The benchmark trusts the manifest.
- Attack addresses use reserved domains only (`*.example`, `*.test`).
