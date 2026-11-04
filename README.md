# GiftCircle 🎁

A self-hosted, open-source gift exchange app for friends, families and work groups. Built with FastAPI, SQLAlchemy, PostgreSQL and plain JavaScript/CSS. Licensed under MIT.

## Features

- Email sign-in links, private groups and invitations.
- Separate exchanges with a budget, date and custom welcome message, including for later invitees.
- One-to-one gift draws, multiple directional exclusions and protection against repeating a previous draw.
- Private recipient reveal links with a tap-to-reveal screen.
- Exchange-specific wish lists, Draft/Finalised status, reservations and purchase tracking.
- Per-exchange Surprise or Show reservations mode.
- Anonymous giver/recipient conversations, group chat and email notifications with links to reply in the app.
- Persistent unread counts for each conversation, exchange and the Messages navigation.
- Responsive desktop/mobile interface, compact gift rows and an installable app shell.
- Organiser controls to remove members before a draw, delete an exchange or delete a group and its exchanges.

## Public source, private installation

This repository contains application code, tests and example configuration. It contains no live installation settings, participant records, messages, wish lists, production database or mail credentials.

Keep actual configuration in a private `.env` file or your host's secret store. Database volumes, backups, logs and credentials belong outside Git. The `.gitignore` and `.dockerignore` exclude local private files; always review staged changes before committing. Replace example addresses with your own only in private configuration.

## Run locally with Docker and PostgreSQL

1. Copy `.env.example` to `.env`.
2. Choose a long, random URL-safe `POSTGRES_PASSWORD`. Set `PUBLIC_URL=http://localhost:8187` for local use.
3. Keep the example Mailpit settings and start the development inbox:

   ```sh
   docker compose --profile devmail up -d --build
   ```

4. Open <http://localhost:8187>. Enter an email address and retrieve its sign-in link from Mailpit at <http://localhost:8025>.

Mailpit captures mail locally; it does not deliver to real inboxes. The app and Mailpit ports bind to the Docker host's loopback interface. Do not expose the development inbox publicly.

## Local Python development

Python 3.12+ is recommended. SQLite is convenient for local development; PostgreSQL is the production deployment database.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=sqlite:///./local.db
export PUBLIC_URL=http://127.0.0.1:8000
export MAIL_MODE=log
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On Windows PowerShell, create the environment and install requirements using `.venv/Scripts/python.exe`, then run `./start-local.ps1`. Sign-in links appear in the ignored `tools/server-mail.log` file. The local script runs in the background; restarting is necessary after Python changes.

`MAIL_MODE=log` is for isolated development only: it writes sign-in and invitation links to local logs. Never use it for a public installation.

## Deploy with real email

- Set `PUBLIC_URL` to your installation's HTTPS address in the private `.env` file.
- Put an HTTPS reverse proxy in front of the app's loopback port, or connect it over a private Docker network.
- Set `MAIL_MODE=smtp`, the provider's SMTP host, port and private credentials. Use `SMTP_STARTTLS=true` for STARTTLS or `SMTP_SSL=true` for implicit TLS, as required by your provider.
- Set `MAIL_FROM` to an address the provider authorises. Use the provider's supported authentication method; do not put your ordinary email password in the repository.
- Start with `docker compose up -d --build` without the development inbox profile.
- Back up the PostgreSQL database and private configuration. Keep a separate backup copy and test restoration before relying on it.

Emails include plain text and HTML, a date and unique message ID. Deliverability also depends on the sending provider, domain authentication and recipient filtering; inbox placement cannot be guaranteed. Replies to notification emails are **not** imported. Each notification links to the correct in-app conversation.

## Tests

```sh
# Set before importing the app so startup uses a disposable local database.
export DATABASE_URL=sqlite:///./test-bootstrap.db
pytest -q tests
node --check app/static/app.js
python tools/ui_release_check.py
python tools/unread_ui_check.py
python tools/modal_pointer_check.py
python tools/welcome_layout_check.py
```

The API suite uses isolated temporary databases and captures email locally. It covers authentication, membership, invitations, draws, exclusions, privacy, wish lists, reservations, deletion, reveal links and per-user unread state. It has also been run against an isolated PostgreSQL database. Never point tests at a database you want to keep.

The browser checks use Playwright with headless Microsoft Edge (`channel='msedge'`) and a synthetic API; they send no real email and use no production accounts. Install Edge or adapt the launch channel to your installed Playwright browser. Generated screenshots remain ignored. Checks cover desktop, tablet and narrow phone layouts, unread navigation, drafts, composer sizing, dialogs and key user flows.

## Privacy and permissions

- Session and authentication tokens are stored hashed. Sessions use HttpOnly, SameSite cookies and Secure cookies when `PUBLIC_URL` uses HTTPS.
- Magic sign-in links expire after 20 minutes and can be used once. Invitations require the invited email account.
- Every exchange request checks group membership and participation. Only the organiser can change reservation mode, exclusions or run the draw.
- Organisers cannot use the app to read other people's anonymous conversations or reveal all assignments. A server/database operator necessarily has access to stored data; this is not end-to-end encryption.
- A recipient's giver identity stays hidden. In Surprise mode their reservations stay hidden too. In Show reservations mode the recipient sees reserved items without the giver's identity.
- A draw email's private reveal link can show its recipient without signing in. Anyone possessing that link can see that one recipient until it expires (30 days) or the exchange is deleted; keep it private.
- Deleting a group deletes its exchanges and associated records for all participants. Deleting an exchange leaves the group and other exchanges intact. Backups are managed separately by the installation owner.

## Operational boundaries

- Draws are final. Create a new exchange rather than resetting a completed draw. People joining later join the group and its undrawn exchanges.
- Read positions are saved per user, exchange and conversation. Opening one conversation leaves the others unread. Messages written before unread tracking was installed initially appear unread until opened.
- Unread badges refresh approximately every eight seconds while the app is visible. Polling preserves drafts and avoids replacing a chat while you are reading earlier messages.
- The service worker caches static assets only. Sign-in, messages and other app functions require a connection.
- The schema is created on startup. Current additive features use separate tables; introduce versioned migrations before changes to existing columns or more complex upgrades.
- Attachments, incoming email replies, push notifications and multiple currencies are not implemented.

## Contributing

Use fictional data and example addresses in tests, keep credentials out of commits, and run the relevant checks before submitting changes. Review privacy and organiser/participant permissions whenever adding an endpoint.

## License

[MIT](LICENSE), copyright GiftCircle contributors.
