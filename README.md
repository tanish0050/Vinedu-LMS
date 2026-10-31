# Vinedu — Engineering Learning Space

A responsive engineering learning space built from scratch for the Vinedu screenshots. The backend uses Python and Flask; PostgreSQL stores accounts and learning data, while the frontend uses plain HTML, CSS and browser JavaScript.

## Run locally

Requires Python 3.10 or later. Locally, SQLite starts automatically so no separate database service is needed. Render uses PostgreSQL for shared student accounts.

```sh
pip install -r requirements.txt
python app.py
```

Open `http://localhost:3000`. Each student creates an account with their name, email and password; their hashed password, login session, quiz results and progress are saved to the local SQLite file during local development. Passwords need at least 12 characters. The local demo admin credentials and recovery code are displayed on the Administrator tab. On Render, students use the shared PostgreSQL database, and admins are provisioned with private `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `ADMIN_RESET_TOKEN` variables. The local demo credentials must not be used online.

## Deploy on Render

1. Push this folder to a GitHub repository.
2. In Render, create a new **Blueprint** and select the repository. If the project is inside a larger repository, set the service root directory to `vinedu-lms`.
3. Review the web service and PostgreSQL database in `render.yaml`. When prompted, enter the admin email and a strong, unique administrator password as private environment variables. Render injects the PostgreSQL URL into the web service. Deploy; Render installs dependencies and runs `npm start`.

Alternatively, create a Render **Web Service** with root directory `vinedu-lms`, build command `pip install -r requirements.txt`, and start command `gunicorn --workers 2 --threads 4 --bind 0.0.0.0:$PORT app:app`; create a PostgreSQL database and set `DATABASE_URL`, `APP_ENV=production`, `ADMIN_EMAIL` and `ADMIN_PASSWORD` in the service's environment variables.

## Included

- Screenshot-inspired, mobile-responsive student sign-up/login screen and engineering green visual system.
- Individual PostgreSQL-backed student accounts, scrypt password hashing, server-generated secure HTTP-only sessions, logout, case-insensitive email handling and throttled login attempts. Administrator authorization is checked server-side.
- Student learning dashboard, responsive navigation, course search, categories, outlines, enrolment and per-account module completion.
- My learning starts with Data Structures & Algorithms, Machine Learning, Artificial Intelligence and Engineering Mathematics. Machine Learning and AI replace Circuit Theory and Thermodynamics in the enrolled-course view; more engineering courses remain available in Explore.
- Five-question subject quizzes, scoring, best attempts and progress saved to each signed-in student's database account.
- Interaction-based activity history, seven-day active-study chart, and CSV export for the administrator preview.
- Local assignment preview, due dates, file selection, demo submission states and administrator assignment creation.
- Online class schedule and secure-link entry (links are added by the learner/admin; Vinedu does not host video calls).
- Reading shelf, bookmarks and local TXT/Markdown/CSV reader.
- Course-outline tutor demo, quick questions and course context. The included tutor is not an AI model or textbook RAG implementation.
- Administrator course add/edit/archive controls backed by the shared catalog; student directory with server-side block/unblock and immediate session revocation; privileged admin password change and recovery-code reset; assignment/session management and CSV analytics export.
- Per-account JSON backup, CSV export, personal settings and reset controls.
- Account-saved light/dark theme, focus timer with 25- and 50-minute study intervals, daily study task planner, personal course notes, learning streaks, and a guided career-skills roadmap.
- Account-saved spaced-repetition flashcards generated from lessons or written by the learner, with Again/Hard/Good/Easy scheduling; achievements are earned from completed learning activity.
- Every course module now opens a short reading with worked examples and a practice prompt. New accounts start unenrolled at 0% progress; lesson completion records real per-student progress.
- Students can upload or remove their own private JPEG/PNG/WebP profile photo (maximum 2 MB). Photos, logins and learning data persist in SQLite locally and PostgreSQL on Render.
- Keyboard-friendly labelled controls, focus styling, mobile layout, and lightweight Node deployment.

## Demo data and production boundary

Vinedu stores account records, salted password hashes, sessions and per-account learning data in PostgreSQL. Sample course outlines, tutor answers, classes and assignments are illustrative. Assignment file selection is still a demo and does not upload or persist actual file contents. The app measures study interactions; it does not treat an open tab as attendance or study time.

This is a working student-account foundation, but needs a security review before use with real institutional records. It does not include email verification, password reset, MFA, per-course permissions or stored assignment uploads. Protect the seeded administrator credentials and database. **Do not collect real assignment files or confidential curriculum until private file storage, access policies, backups, account recovery and institution privacy requirements are configured.**

For broader production use, add email verification, MFA or a trusted OIDC provider, stronger account recovery, per-course permissions, private file storage, database backups and audit logs. Set `ADMIN_RESET_TOKEN` to a long, private recovery secret in Render so the administrator can reset a forgotten password. For the institutional AI tutor, add a private backend with permission-aware retrieval over approved, OCR-processed materials; never place model API keys in browser code. Add a conferencing provider for actual live sessions.

**Render free-plan note:** the included Blueprint creates a free PostgreSQL database to make first deployment straightforward. Render currently expires free PostgreSQL databases after 30 days and later deletes expired data after a grace period. Upgrade the database plan before relying on student accounts or long-term learning history; free web services and databases are intended for previews, not production.

## Configuration

Gunicorn reads `PORT` from the environment and binds to `0.0.0.0`. On Render, `DATABASE_URL` comes from the managed PostgreSQL service. Set a strong `ADMIN_PASSWORD` (minimum 16 characters) and `ADMIN_EMAIL` to provision the administrator account; these must stay private and must not be committed to source control. Local-demo credentials are shown under the Administrator login; deployed administrator passwords are never sent to the browser.
