# Stellenpilot multi platform architecture

Status: proposal, October 2026. Owner: Sourav Sarker. Client framework decided: Flutter.

## 1. The one decision that matters

Stellenpilot today is about 9,300 lines of Python: job sources, scoring, the truth guard, CV tailoring, Gmail sync, the scheduler and the built in llama.cpp model. All of that is the product. The web dashboard (`stellenpilot/web/index.html`) is only a window onto it.

So the rule is:

**One engine, many shells.** The Python engine stays the single place where business logic lives. One Flutter app (Dart) is the thin native shell on every platform. It talks to the engine through a versioned HTTP API. Nothing about scoring, tailoring or the truth guard is ever rewritten in a second language.

Rewriting the engine in another language would mean several truth guards that drift apart, three sets of scrapers to fix every time a job board changes its HTML, and three test suites. For a one person open source project that is not survivable.

## 2. Target picture

```
                 ┌────────────────────────────────────────────┐
                 │            Stellenpilot Engine (Python)    │
                 │                                            │
                 │  sources/  pipeline  score  tailor  llm    │
                 │  cv_parse  gmail_sync  schedule  builtin   │
                 │  db (SQLite)  ~/.stellenpilot              │
                 │                                            │
                 │  API layer:  /api/v1/...  (OpenAPI spec)   │
                 └──────────────▲────────────▲────────────────┘
                                │            │
               localhost        │            │   LAN or tunnel, paired + TLS
               ┌────────────────┘            └──────────────┐
               │                                            │
     Flutter app, desktop build                  Flutter app, mobile build
     Windows, macOS, Linux                       Android, iPhone, iPad
     hosts the engine as a child process         remote client only

     Web dashboard (existing) stays available on localhost.
```

Desktop apps (Windows, macOS) **host** the engine on the same machine. Phones **connect** to an engine running somewhere else (the user's PC, a home server, or Docker). Phones never run the engine.

## 3. Why phones cannot run the engine

1. The built in AI is a multi gigabyte llama.cpp model. Running it on a phone drains the battery and is very slow.
2. iOS and Android kill background work. A daily search over 6 sources plus about 200 company sites will not finish reliably in the background.
3. iOS does not allow running a bundled Python interpreter as a server in a way the App Store accepts for this use case.
4. The privacy promise ("your CV never leaves your computer") stays true if the phone talks to the user's own computer, not a cloud.

## 4. Layers of the engine

| Layer | Today | Change needed |
|---|---|---|
| Sources | `sources/*.py`, `watchlist` | none |
| Core logic | `pipeline`, `score`, `tailor`, `evaluate`, `cv_parse`, `importer` | none |
| AI | `llm`, `builtin` | none |
| Storage | `db.py`, SQLite, files in `~/.stellenpilot` | add a schema version table and migrations |
| Integrations | `gmail_sync`, `mail_imap`, `notify` | none |
| Scheduling | `schedule.py` | none |
| API | `server.py`, stdlib `http.server`, routes like `/api/state`, `/api/jobs/...` | **main work, see section 5** |
| Desktop OS glue | `shortcut`, `launch`, `open-folder`, `open-doc` | move behind a "host" capability, clients do these natively |

## 5. The API contract (the real deliverable)

Everything depends on this. Steps:

1. **Version the routes.** Move `/api/*` to `/api/v1/*`. Keep the old paths as aliases for the web dashboard until it is migrated.
2. **Write an OpenAPI 3.1 spec** in `api/openapi.yaml`. It is the source of truth.
3. **Generate the Dart client from the spec**, never hand write it: openapi-generator with the `dart-dio` generator. Regenerate on every spec change.
4. **Contract tests** in CI: run the engine, hit every endpoint, validate responses against the spec. A client break then shows up in CI, not in an app store review.
5. **Replace polling with events** where it matters: `/api/v1/progress` becomes Server Sent Events, so phones get live run progress without polling every second.

Core resources:

| Resource | Operations |
|---|---|
| `state` | dashboard summary |
| `jobs` | list, filter, get, patch status, rate, notes |
| `jobs/{id}/docs` | download tailored CV and cover letter (docx, pdf) |
| `runs` | start a search, read history, live progress (SSE) |
| `profile` / `cv` | import, read, save, reread |
| `settings` | read, update |
| `ai` | model status, download built in model |
| `gmail` | status, connect, disconnect |
| `host` | desktop only: open folder, create shortcut |

Mail, AI downloads and file system actions stay on the engine machine. Phones only read results and change job state.

## 6. Security: the part that does not exist yet

Today the server binds to `127.0.0.1` with no authentication. That is fine for one machine and wrong the moment a phone connects. Before any mobile client ships:

1. **Pairing.** The desktop shows a QR code with engine address, a one time code and the certificate fingerprint. The phone scans it and receives a long lived device token.
2. **Token auth** on every request (`Authorization: Bearer`). Tokens are listed in Settings and can be revoked per device.
3. **TLS** with a self signed certificate generated on first run. The phone pins the fingerprint from the QR code, so no certificate authority is needed.
4. **Bind address stays `127.0.0.1` by default.** Remote access is an explicit switch in Settings.
5. **Reachability outside home:** recommend Tailscale or WireGuard rather than opening a port on the router.
6. **Keep the existing browser guard.** `server.py` already refuses foreign `Host` headers (DNS rebinding) and requires the `X-Jobhunt` header plus a local `Origin` (CSRF). That guard will also refuse a phone, by design. Remote mode therefore needs a second path: requests that carry a valid device token over TLS skip the Host check, everything else keeps the current rules.

## 7. The Flutter app

One Dart codebase, two roles decided at runtime.

### Shared code (all platforms)
* **UI:** Flutter, Material 3, themed with the existing Stellenpilot colors and the Geist font, so it looks like the web dashboard.
* **State:** Riverpod.
* **Networking:** the generated `dart-dio` client. Live run progress over Server Sent Events.
* **Secrets:** device token in `flutter_secure_storage` (Keychain on Apple, Keystore on Android).
* **Certificate pinning:** a custom `HttpClient` that accepts only the certificate fingerprint received during pairing.
* **Screens:** pairing (QR scan), home, jobs with score, reason and gaps, job detail, applications, documents (open the tailored PDF), settings.
* **No business logic.** If the app needs a rule ("is this job closed?"), the engine returns it as a field.

### Desktop role (Windows, macOS, Linux)
* Bundles the frozen engine (PyInstaller, already used in the repo's Windows and macOS workflows).
* Starts it with `Process.start` on a random local port, waits for `/api/v1/health`, stops it on exit.
* Talks to it over `127.0.0.1`. No pairing needed on the same machine.
* Shows the pairing QR code so phones can connect.
* Native extras: tray icon, system notifications, start at login.

### Mobile role (Android, iPhone, iPad)
* Remote client only. Pair once, then browse jobs, read reasons and gaps, mark good or bad match, open documents, change status.
* Android: optional periodic "new matches?" check with WorkManager while on the home network.
* Push notifications: later. Needs a small relay (Firebase Cloud Messaging, which also delivers to iOS), so start with refresh on open.

### Platform code
Flutter covers almost everything. Small pieces of Kotlin (Android) or Swift (iOS, macOS) are written only through platform channels if a plugin is missing.

### Build requirements
* Android: builds on Windows or Linux. Google Play account is a one time fee.
* iOS and macOS: need Xcode, so a Mac or a macOS CI runner (the repo already has a macOS workflow). Publishing needs the Apple Developer Program, about 99 USD per year.

## 8. Repository layout

Keep one monorepo while it is a one person project:

```
stellenpilot/
  stellenpilot/          Python engine (unchanged location, PyPI package)
  api/openapi.yaml       the contract
  app/                   Flutter app (lib/, android/, ios/, macos/, windows/, linux/)
    lib/api/             generated Dart client, never edited by hand
  .github/workflows/     engine tests, contract tests, Flutter build per platform (path filters)
```

## 9. Order of work

1. **Freeze the contract.** Version routes, write `openapi.yaml`, add contract tests, generate the Dart client. No app yet.
2. **Security.** Pairing, tokens, TLS with pinning, revocation. Ship it in the Python app first, behind the remote access switch.
3. **Flutter mobile, Android build first.** Sideload on your own phone, prove pairing and the remote model.
4. **iPhone build** of the same app, through a Mac or macOS CI, then TestFlight.
5. **Flutter desktop** hosting the engine, replacing the current launcher only once it is better than the web dashboard.

Ship each step as a release. Do not start step 3 before step 2 is done.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Engine API changes break the app | OpenAPI contract tests in CI, `/api/v1` kept stable, breaking changes go to `/api/v2` |
| Users expose the engine to the internet | remote access off by default, pairing plus tokens plus TLS, Tailscale recommended |
| Phone shows stale data when PC is off | show "last synced" clearly; optional later: engine on an always on box (Docker image already exists) |
| Two codebases (Python and Dart) for one maintainer | generated client, no logic in the app, desktop build only when it beats the web dashboard |
| Flutter desktop less polished than native | keep the web dashboard as fallback; desktop is the last step |
| App store review rejects a client that needs a home server | demo mode with fictional data (the repo already has `demo.py`) so reviewers can use the app |
