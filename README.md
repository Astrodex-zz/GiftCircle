# GiftCircle 🎁

**Make memories. Not spreadsheets.** A calm, private, open-source Secret Santa and family gift-exchange application. No ads, tracking, account passwords or affiliate shopping lists.

![Desktop dashboard](tools/ui-dashboard-desktop.png)

## Features delivered

- Passwordless email magic links (single-use; 20-minute expiry) and 30-day HTTP-only sessions
- Family groups, email invitations bound to the recipient's email address, and organiser-only controls
- Reusable groups and separate events, budgets and exchange dates
- Secret-Santa matching, no self-draws, one-to-one recipient assignment, directional exclusions, impossible-draw validation
- Sealed assignments: even the organiser cannot view everyone's giver/recipient pairs
- Personal wish lists with descriptions, external HTTPS/HTTP links and optional price
- Gift reservations and purchase status hidden from the wish-list owner
- **Private anonymous two-way conversations** between giver and recipient; separate family chat
- Organiser announcements and optional email notifications, in-app notification history
- Mobile-first responsive interface with installable PWA shell, no mandatory app store account
- Docker Compose, PostgreSQL, optional Mailpit development inbox, Traefik-compatible deployment
- MIT license and integration tests

## Architecture

FastAPI + SQLAlchemy + PostgreSQL backend. The frontend uses **plain, dependency-free JavaScript and CSS** for zero-build offline installation. This is an intentional simplification compared with the earlier React proposal: fewer dependencies, faster self-hosting and no CDN/runtime dependency. If React/TypeScript is required later, the API is separate and can be used unchanged. The UI has been checked in desktop and mobile Chromium with mocked API responses.

## Quick start (Docker)

1. Copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD` with a random secret. Set `PUBLIC_URL` to the HTTPS URL family members will actually use.
2. For local development email testing, leave `SMTP_HOST=mailpit` and run:

   ```bash
   docker compose --profile devmail up -d --build
   ```

3. Make your HTTPS reverse proxy forward to `http://127.0.0.1:8187` **on the Docker host**. The app binds only to localhost by default. With Traefik in another Docker network, either route via the host gateway or attach the app to Traefik's network and adjust Compose appropriately.
4. Open the URL and enter your own email. With development Mailpit, read the magic link in the mail inbox at `http://127.0.0.1:8025` on the Docker host (do not expose the Mailpit UI publicly). If connecting from another computer, use SSH port forwarding or access Mailpit locally.
5. Sign in, create a family, invite relatives, add an exchange and draw names after everyone joins.

**Important:** Development Mailpit captures messages; it does not send to real family inboxes. To go live, enter your actual SMTP host, authenticated username, app password/token and `MAIL_FROM` address in your private `.env` file; then run `docker compose up -d --build` **without** the `devmail` profile. Use your provider's TLS options (`SMTP_SSL=true` on port 465 or `SMTP_STARTTLS=true` on port 587, as applicable). Never send me credentials or commit `.env` to GitHub.

Only one sending address is required. Real family members use their personal emails for invitations and magic links. Outbound mail should be sent from a domain verified with SPF/DKIM/DMARC for deliverability.

### Local Python development (SQLite)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=sqlite:///$(pwd)/local.db
export PUBLIC_URL=http://127.0.0.1:8000
export MAIL_MODE=log
uvicorn app.main:app --reload
```

`MAIL_MODE=log` writes one-time links into application logs for local development **only**. Do not use that mode on a public server.

## Testing

```bash
pytest -q tests
node --check app/static/app.js
python tools/ui_smoke.py
```

The Python integration suite uses isolated temporary SQLite databases and exercises signup, email invitation acceptance, three-person drawing, exclusions, wish lists, reservations, purchases, anonymous message exchange, permissions and sign-out. `ui_smoke.py` runs desktop/mobile Chromium interactions using a deterministic mock API, checking responsive layout and click flows.

`tools/browser_walkthrough.py` is a live-server Chromium walkthrough, provided for running on your own machine. It was **not executable in the build environment** because the managed Chromium browser blocks navigation to all URLs. No claim of full live-browser end-to-end verification is made. Docker/PostgreSQL/real SMTP delivery also require verification on a Docker-equipped machine.

## Privacy model

- Sessions are random, hashed server-side and sent as `HttpOnly` `SameSite=Lax` cookies, with `Secure` enabled when `PUBLIC_URL` is HTTPS.
- Magic links and invitations contain single-use random tokens, stored hashed; invite acceptance requires signing in with the invited email.
- Family membership is checked on every exchange request.
- Assignment endpoints only reveal the viewer's own recipient and own anonymous conversation IDs. Another family member cannot fetch someone else's secret conversation or wish list.
- Anonymous message API returns only whether each message was authored by the current viewer, never a hidden sender ID. Email notifications contain neither the sender's name nor the private message body.
- Gift reservations and purchase status are not returned to the wish list's owner.
- Browser-typed text is escaped before insertion into the DOM; product links allow only HTTP(S).
- Group owners can publish announcements and configure matching, but have no privileged access to other participants' secret chats.
- Sensible security headers, a 15-minute email-request rate limit, foreign-Origin rejection and no-cache API responses are enabled.

## Operational notes and intentional V1 boundaries

- **Do not change an exchange after drawing.** A new exchange must be created to avoid breaking secret conversation identity and reservations. Invitees joining after a draw can join the family but are not retroactively added to that exchange.
- Family chat and anonymous chats use a lightweight 8-second browser refresh rather than WebSockets.
- Push notifications, replying directly to emails, file attachments, historical-pair avoidance, passkeys, support for different currencies, granular participation selection and database migration tooling are future improvements.
- The app uses a create-on-start schema, appropriate for the initial release; back up PostgreSQL before applying future schema upgrades. Add versioned migrations before major multi-version deployments.
- When deploying publicly, put HTTPS in front, back up the PostgreSQL volume, use a reliable SMTP provider, keep Python/PostgreSQL images updated and test recoveries.
- The API tests currently run with SQLite; PostgreSQL configuration is included, but a PostgreSQL container could not be launched in the authoring environment because Docker was unavailable.

## Traefik example

When Traefik runs outside the GiftCircle Compose project, you can point a Traefik service URL to `http://<docker-host-lan-ip>:8187` only after adjusting the binding to permit traffic from the proxy. **Do not** expose the plaintext backend port to the public internet. A shared Docker network and Traefik labels is preferable; modify `compose.yaml` appropriately for your network and hostname.

## License

MIT — see `LICENSE`.
