# Screenshots

How the images in this folder are produced, so the next person refreshing them
does not have to work it out again — and so nobody is tempted to take them from a
live deployment.

## Rules

- **Never screenshot a real tenant, and never screenshot a deployed instance.**
  Every image here comes from a throwaway local stack seeded with demo data.
- The stack used for screenshots has **no tenant credentials configured at all** —
  no tenant ID, no client ID, no secret, no Azure OpenAI key — so it cannot make a
  Graph or Azure OpenAI call even by accident.
- Both themes, every time. A light screenshot without its dark twin is a
  half-finished change, because dark mode is where card and border regressions
  hide.

## Naming

`<page>.png` for light, `<page>-dark.png` for dark. The Overview keeps its
historical name `executive-summary` rather than being renamed, so existing links
to it — including from the suite's landing page — keep working.

| File | Page |
|---|---|
| `executive-summary(-dark).png` | Overview |
| `executive-briefing(-dark).png` | Executive briefing |
| `usage-breakdown(-dark).png` | Usage breakdown |
| `prompt-quality(-dark).png` | Prompt quality |
| `conversation-detail(-dark).png` | Conversations, with a conversation open |
| `people-coaching(-dark).png` | People coaching (organisation) |
| `tenant-users(-dark).png` | Tenant users |
| `personal-coaching(-dark).png` | Your coaching |
| `settings(-dark).png` | Settings |

## Producing them

1. Bring up the stack from a clean database. `.env` needs only a `FERNET_KEY`, a
   `SECRET_KEY` and an `ADMIN_PASSWORD`; leave every tenant field empty.

   ```bash
   cp .env.example .env
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   # paste into FERNET_KEY, set ADMIN_PASSWORD, then:
   docker compose up -d --build
   ```

2. Seed enough data that the charts have shape. A couple of hundred
   conversations spread over 90 days gives period-on-period movement for the
   briefing; forty does not.

   ```bash
   docker compose exec api python -m scripts.seed_demo --conversations 220 --reset
   ```

   The seeder writes a fourteen-person directory with departments, offices,
   countries and a reporting line, gives each person a different prompting skill
   so the coaching pages have someone to coach, leaves two people licensed with no
   activity, and binds the admin account to one of them so the personal pages can
   be reached without Entra.

3. Sign in as the local admin and walk every page in the nav, light and dark. The
   theme toggle is at the bottom of the sidebar.

4. Capture at a desktop viewport — **1600×1000** matches the existing images.
   These are desktop dashboards; there is no narrow-width layout to capture.

5. Drop the files in this folder using the names above, and check the README
   still describes what the picture shows.

## Gotchas

- If the browser doing the capture runs on a different host from the stack, bind
  the API to `0.0.0.0` (the compose file already does) and browse the host's
  address rather than `localhost` — `localhost` in that browser is its own
  container.
- The demo persona binding means the sidebar shows a seeded person's name, not
  `admin`. That is correct and is what the personal-page screenshots should show.
- Stop and delete the stack afterwards (`docker compose down -v`). Its Postgres
  volume holds nothing but demo data, and leaving it running invites somebody to
  point real credentials at it.
