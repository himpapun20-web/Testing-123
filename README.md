# CCTV Survey Report Automation — VS Code Export

A standalone, data-driven CCTV engineering-report generator. It creates reports from the project, pipe-section, inspection, video, site-plan and event data entered for that project. It is not a static sample report.

## Local-only authentication

This export provides an optional development login so it can run without Manus OAuth. The VS Code setup writes `CCTV_AUTH_MODE=local` and `APP_ENV=development` in the ignored `.env.vscode`; the API signs in as the seeded synthetic administrator. Local login is accepted only for loopback clients (`127.0.0.1`, `::1` or `localhost`) and fails closed outside development. The supplied launch tasks bind the API and frontend to `127.0.0.1`.

The API also loads `.env.vscode` from the project root when started directly, so the local login configuration applies even when the VS Code shell tasks are not used. In local mode, the sign-in endpoint returns to the app without starting an OAuth flow.

This is developer convenience, **not production authentication**. Do not expose local mode through a tunnel, reverse proxy or public network. The public launcher below switches to application-managed password authentication and HTTPS; other network deployments must use an appropriate authentication, TLS, authorization and upload-limit configuration. OAuth values in `.env.vscode.example` remain blank and are not required by local mode.

## Features

- Company, user/role, project, pipe-section, asset and inspection CRUD backed by SQLAlchemy and Alembic.
- PostgreSQL-compatible schema, migrations and idempotent synthetic seed data.
- Project dashboard with project, pipe-section, inspection and report status.
- Responsive evergreen survey-workbench interface with a branded secure entry screen, clear navigation, readable data tables and accessible mobile controls.
- Batch upload for up to 50 CCTV videos. Each reviewed filename creates a real video asset and inspection record; duplicate filenames remain separate uploads.
- Video batch uploads show transfer progress, and individual files can be removed from the review queue before upload.
- Filename parser for survey date/date range, optional road/location, Start/Finish Manhole, `(US)`/`(DS)`, material code, diameter and length. Review and correct the suggestions before saving.
- A real Site Layout Plan image upload for Appendix I. No missing plan is replaced with an invented drawing.
- Manual event entry by video timestamp and pipe distance. FFmpeg extracts the actual video frame; unreadable media or an invalid timestamp is rejected.
- English A4 report preview and PDF. Appendix III contains the section-distance timeline on the left and event details on the right, followed by portrait Section Pictures sheets with the real still, photo number, time, distance, event description, clock reference and MSCC5 code when entered.
- Fixed Statement of Conformity and Method Statement text are editable in report-content records; variable client, project and contractor fields come from the selected project's saved records.

Video contents are **not** AI-analyzed. Defect descriptions, clock positions and MSCC5 codes are entered and checked by an authorized user; the application does not assign a defect, code, grade, risk score or engineering recommendation.

## Supported filename format

```text
YYYY-M-D[^D] [Location] StartNode to FinishNode (US|DS)(Material)(Diameter) Lengthm CCTV.<video extension>
```

`US` means Upstream and `DS` means Downstream. Location and a same-month day range are optional. The first date in a range becomes the inspection date; the date range contributes both dates to the project's survey period.

The parser includes these supplied examples:

```text
2026-10-27 RWSP-B2-02 to GNB (US)(DI)(150) 0.87m CCTV.mp4
2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mp4
2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mp4
2026-8-28^29 Westlands Road G21 to S60 (DS)(CO)(225) 6.87m CCTV.mp4
2026-8-28^29 Westlands Road S76 to G38 (US)(PVC)(150) 2.67m CCTV.mp4
```

For `2026-8-28^29`, the inspection date is 28 August 2026 and the range end is 29 August 2026. A repeated filename is not treated as a duplicate upload: every file has its own asset, inspection and automatic sequence number for its pipe section.

## Report sequence

1. Cover Page
2. Statement of Conformity
3. Contents
4. Introduction
5. Method Statement
6. Summary of Pipelines Condition & Site Environment
7. Appendices divider
8. Appendix I — Site Layout Plan
9. Appendix II — CCTV Survey Report: Project Information; Survey Overview; Section Summary; Detailed Section Report; Defect Summary; Section Profile; Scoring Summary; Survey Status and Uncertainty Notes
10. Appendix III — Photographic Sheet: per-inspection distance/timeline and event details, followed by Section Pictures pages with repeatable Item No., Inspection Direction, PLR, Client's Job Ref and Contractor's Job Ref metadata.

The supplied Lamma report guides the implementation's target of 90–100% layout similarity and fixed wording only. Its client name, location, dates, pipe records, site plan and CCTV photographs are not copied into user reports. Any missing site plan or frame is identified as not provided; no synthetic image is presented as field evidence.

## Requirements

Install Python 3.12+, Node.js 20+ with Corepack, Docker with Compose v2, and VS Code. Linux/WSL may also require Pango and font libraries for WeasyPrint. PostgreSQL 16 is used by the included Docker Compose setup.

## Open and run in VS Code

1. Extract the ZIP and open `cctvreport-vscode.code-workspace` in VS Code.
2. Run **CCTV: Setup local PostgreSQL, migrations and seed** once. It installs dependencies, creates the ignored `.env.vscode`, starts PostgreSQL, applies migrations and inserts synthetic records. The sample database password is for local development only; change the password and DSN together if needed.
3. Run **CCTV: API (local)** and **CCTV: Web (local)** in two terminals.
4. Open `http://127.0.0.1:3000`. The seeded local administrator is `admin@example.test`; no Manus account or OAuth secret is required in local mode.
5. Stop PostgreSQL without deleting its Docker volume with `docker compose --env-file .env.vscode stop postgres`.

## Start the website on Windows

After completing setup once, double-click `Start CCTV Website.cmd` in the project folder. It starts the local API and website in the background, opens `http://127.0.0.1:3000`, and saves service logs under `.local-run/`. Double-click `Stop CCTV Website.cmd` to stop services started by the launcher. Keep the project folder in place; uploaded videos and other evidence are stored locally.

## Use the website on the same Wi-Fi

To let other computers on the same trusted private network use the app without Tailscale:

1. Double-click `Start LAN CCTV Website.cmd` on the computer that stores the app and data. If prompted, configure the administrator email and password in the PowerShell window; the password is not echoed.
2. The launcher prints the computer's LAN address, such as `http://192.168.1.20:8001`. Open that address from another computer on the same Wi-Fi and sign in with an account created by an administrator.
3. If Windows Firewall blocks the connection, open PowerShell as Administrator on the host computer and run:

   ```powershell
   New-NetFirewallRule -DisplayName "CCTV LAN Website" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8001 -Profile Private -RemoteAddress LocalSubnet
   ```

   Remove the rule later with `Remove-NetFirewallRule -DisplayName "CCTV LAN Website"`.
4. Keep the launcher window open while the app is in use. Press Ctrl+C in that window to stop the LAN server.

This LAN launcher uses application-managed password sign-in, but serves plain HTTP: passwords and app traffic are **not encrypted** on the Wi-Fi network. Use it only on a trusted private network; do not use it on public Wi-Fi or forward port 8001 through your router. For use over the internet, use the separate HTTPS public launcher or a properly configured HTTPS host.

## Deploy a disposable demo to Render

The root `Dockerfile` and `render.yaml` configure a public, password-protected demo using Render's free web-service plan. This deployment seeds synthetic sample records at startup and stores the SQLite database and uploaded files on temporary storage. **Do not use it for real CCTV footage or records:** free-service restarts, sleeps, or redeploys can remove changes and uploaded files.

1. Add the `Dockerfile`, `render.yaml`, and `backend/app/render_startup.py` files to your GitHub repository, then push them to the branch you plan to deploy.
2. In Render, choose **New → Blueprint**, connect that repository, and select the branch. Review the `cctv-report-demo` web service before deploying.
3. When prompted for the unsynced variables, enter `DEMO_ADMIN_EMAIL` and a unique `DEMO_ADMIN_PASSWORD` of at least 12 characters. Render generates `CCTV_AUTH_SECRET`; keep it private.
4. Deploy and wait for the service health check at `/api/health` to pass. Use the Render URL and the admin email/password you configured to sign in.
5. Test using only synthetic/non-sensitive information. Do not rely on uploaded videos or database changes surviving a free-service restart.

The Docker image builds the frontend and serves it from FastAPI, including the PDF browser dependency. This demo does not include a persistent database or persistent file storage. For real data, switch to a paid hosting plan with durable storage or configure suitable external PostgreSQL and object storage before deployment.

## Share the website with invited users

The public launcher uses Tailscale Funnel to provide a public HTTPS link while this computer is on. This requires installing Tailscale, signing in, and enabling Funnel in the Tailscale admin console; Tailscale account availability and limits apply. The tunnel is only started by the public launcher. Use your own email address when setting up the initial administrator; the seeded `@example.test` account is only for local development.

1. Install Tailscale for Windows, sign in, and enable Funnel for your tailnet.
2. Double-click `Start Public CCTV Website.cmd`. The launcher applies the password-auth database migration, builds and serves the production frontend, creates a private signing secret, and asks you to set an administrator password if none exists.
3. Keep the PowerShell window open. Copy the `https://…ts.net` link shown by `tailscale funnel status` and share it only with people you trust.
4. Create each person's user record in the Users page and use its **Set password** action. Send each person their sign-in details through a separate secure channel. There is no public registration.
5. Press Ctrl+C in the launcher window to stop the public link and local API.

The computer must remain on and connected to the internet. This app is designed for one trusted company per deployment; it does not isolate projects or records between multiple companies. Tailscale Funnel makes the site public, so use strong unique passwords, grant users only the roles they need, and keep Windows and the app updated. Uploads use your computer's internet connection and are subject to your provider's data limits. This free/personal arrangement has no uptime guarantee.

## Create a report from your own inputs

1. Create a project and enter its client, project/report dates, location, TV reference and any available job/contractor references.
2. Open **Generate project report** for that project, select one or more CCTV videos and inspect the filename-derived values. Correct the reviewable date, endpoints, direction, material, diameter, length or location if necessary, then upload the batch. The application creates pipe sections and inspections and assigns internal sequence numbers automatically. It infers a blank project location only if every reviewed row provides the same nonblank filename location, and never overwrites a location already entered on the project.
3. Optionally upload a real PNG, JPEG or WebP Site Layout Plan image (maximum 25 MiB) in the project's Appendix I area.
4. Open **Defects & Photos**, select the appropriate inspection and video, then enter the event type, video timestamp in seconds, section distance in metres, observation, and optional clock position/MSCC5 code. Saving extracts an actual frame from the video at that timestamp.
5. Review the English HTML report and select **Generate / download PDF**. The output reflects the selected project's current saved records and evidence.

The Inspection form does not ask the user to re-enter Inspection No., Operator, Camera, Vehicle, Weather, Legal Status, Inspection Status or Inspection Time. Existing historical database columns may remain for compatibility; the sequence number is assigned by the application.

## Configuration and API

- FastAPI interactive documentation is available at `http://127.0.0.1:8000/docs`.
- PDF reports use WeasyPrint when its native libraries are available. Otherwise, the backend can use installed Microsoft Edge or Google Chrome in headless mode; set `CCTV_PDF_BROWSER` to the browser executable path to select it explicitly.
- The default local evidence store is `storage/`; back it up or replace it with durable, access-controlled object storage before production.
- Maximum video upload defaults to 2 GiB (`CCTV_MAX_VIDEO_UPLOAD_BYTES`). Site-plan image limit defaults to 25 MiB (`CCTV_MAX_SITE_PLAN_UPLOAD_BYTES`). Set reverse-proxy/request-body limits as well, because multipart parsing occurs before application-level validation.
- Project and company row-level tenant isolation, full AI video analysis, automatic defect classification, official MSCC5 grading, risk scoring, automatic recommendations and formal report approval/version release are outside the current scope. Use one trusted company per deployment until tenant-level authorization is implemented.

## Run checks

```bash
PYTHONPATH=backend python -m pytest -vv
corepack pnpm check
corepack pnpm build
pyright --project pyrightconfig.json backend/app backend/tests
```

The integration tests cover the five supplied filename examples, duplicate batch files, PostgreSQL-compatible direction values, form-field omissions, project-driven English report content, valid/invalid uploads, generated-video frame extraction, event linkage, Site Layout Plan image rendering and PDF output.
