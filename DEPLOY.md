# Deploying to Railway

The app runs as a single Streamlit web service in a Docker container. Railway builds the
image, injects `$PORT`, and supplies the API key at runtime. **No credential is ever baked
into the image or committed to the repository.**

---

## Before you start

**Rotate both API keys that were pasted into chat** - the Anthropic key and the Resend
key. Any key that has appeared in a chat transcript, a screenshot or a support ticket
should be treated as public. Create replacements at
<https://console.anthropic.com/settings/keys> and <https://resend.com/api-keys>, delete
the old ones, and use the new values everywhere below.

Set a spend limit on the key while you are there. This app calls the model up to four
times per analysis and costs roughly **$0.10–$0.25 per deck** at Opus pricing; an
unattended public URL is the only realistic way to run up a surprising bill, and the
password gate below closes that hole.

---

## 1. Push the repository

Railway deploys from a Git repository. Confirm the credential files are excluded first:

```bash
git check-ignore -v .env        # must print a .gitignore match
git status --short              # .env must NOT appear
```

Then push to GitHub as normal.

---

## 2. Create the service

**Dashboard:** New Project → Deploy from GitHub repo → pick this repository. Railway reads
`railway.json`, builds `Dockerfile`, and serves the healthcheck at `/_stcore/health`.

**CLI:**

```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

---

## 3. Set the variables

Dashboard → your service → **Variables**, or from the CLI:

```bash
railway variables \
  --set "ANTHROPIC_API_KEY=sk-ant-api03-YOUR-ROTATED-KEY" \
  --set "ANTHROPIC_MODEL=claude-opus-5" \
  --set "LLM_PROVIDER=anthropic" \
  --set "APP_PASSWORD=choose-a-long-random-passphrase" \
  --set "MAX_UPLOAD_MB=64" \
  --set "PAGE_SIZE=letter" \
  --set "ENABLE_PUBLIC_RESEARCH=false" \
  --set "RESEND_API_KEY=re_YOUR-ROTATED-KEY" \
  --set "REPORT_EMAIL_TO=Info@tencapital.group" \
  --set "RESEND_FROM=TEN Capital <reports@tencapital.group>"
```

| Variable | Required | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | **Yes** | Without it the app still runs, but falls back to rule-based extraction and says so on screen |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-opus-5` |
| `LLM_PROVIDER` | No | `anthropic` (default), `openai`, or `local` |
| `APP_PASSWORD` | **Yes in production** | The app *refuses to serve* on Railway without one — see below |
| `MAX_UPLOAD_MB` | No | Upload ceiling. Image-heavy decks run past 50 MB |
| `PAGE_SIZE` | No | `letter` or `a4` |
| `ENABLE_PUBLIC_RESEARCH` | No | Leave off unless you also set a search backend key |
| `RESEND_API_KEY` | No | Turns on email. Without it the app generates normally and reports `Email skipped` |
| `REPORT_EMAIL_TO` | No | Defaults to `Info@tencapital.group` |
| `RESEND_FROM` | No | Must be on a domain verified in Resend. `tencapital.group` is verified |
| `ENABLE_EMAIL` | No | Set `false` to suppress all email without removing the key |
| `PORT` | No | Injected by Railway; do not set it yourself |

### The password gate is not optional

A public Streamlit URL with your key behind it is a machine that converts strangers into
Anthropic charges. The app therefore detects that it is running on a hosting platform
(via `RAILWAY_ENVIRONMENT` and friends) and, if `APP_PASSWORD` is unset, shows an error
and stops instead of serving the upload form. Set the password before your first deploy
and you will never see that screen.

---

## 4. Generate a domain

Dashboard → Settings → Networking → **Generate Domain**, or:

```bash
railway domain
```

Open the URL, enter the password, upload a deck, and press **Build the map**.

---

## 5. Verify the deployment

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://YOUR-APP.up.railway.app/_stcore/health
# expect 200
```

Then, in the browser:

1. The password screen appears — the gate is live.
2. Upload `sample_data/helios_diagnostics_deck.pdf` plus the CSV and notes files.
3. The run finishes with lead candidates and a downloadable one-page PDF.
4. The sidebar shows **Analysis engine: anthropic** with no key warning at the top.
5. The page reports **Emailed to Info@tencapital.group**, and the message arrives with the
   one-pager and CSV attached.

If the banner says the key is missing, the variable did not reach the container — check
for a typo in the variable name and redeploy.

### If email does not arrive

The app reports what happened rather than failing silently, so start with the on-screen
message and `railway logs`:

| Message | Cause |
| --- | --- |
| `Email skipped: no RESEND_API_KEY configured` | The variable is not set on the service |
| `Email skipped: email disabled` | `ENABLE_EMAIL` is false |
| `Email failed: … verify a domain …` | `RESEND_FROM` is not on a verified domain |
| `Email failed: Resend rejected the API key` | Wrong or revoked key |
| `Email failed: could not reach Resend` | Network or Resend outage — the analysis still completed |

An email failure never affects the analysis: the PDF, JSON, sources and CSV are all
produced and downloadable regardless, and the failure is recorded in the JSON warnings.

---

## Operational notes

**Storage is ephemeral.** Railway containers have no persistent disk, and this app does
not use one: each run writes into a temporary directory and the results are handed to the
browser as downloads. Anything a user wants to keep must be downloaded during the session.

**One replica.** `numReplicas` is 1 deliberately. Uploads and in-flight results live in
the process's memory, so a second replica would serve some requests from a process that
knows nothing about them. Scale up only after moving state to shared storage.

**Cold starts.** The first request after a deploy takes a few seconds while Streamlit
boots. The healthcheck timeout is 180 s to allow for this.

**Legacy `.ppt` files.** These need LibreOffice, which is commented out in the
`Dockerfile` because it adds roughly 450 MB. Uncomment that block if your senders still
use the binary PowerPoint format; `.pdf` and `.pptx` work without it.

**Timeouts.** A full analysis with the model takes 60–120 seconds on a large deck.
Streamlit keeps the connection open, so no proxy timeout tuning is needed at this size.

**Logs.**

```bash
railway logs
```

Model failures, unreadable files and schema-validation retries all log a warning line and
degrade the run rather than ending it, so the logs are the place to look when an output
seems thinner than expected.

---

## Running the container locally

Worth doing once before you deploy, because it exercises the exact image Railway builds:

```bash
docker build -t lead-investor-map .
docker run --rm -p 8501:8501 \
  -e ANTHROPIC_API_KEY="sk-ant-api03-YOUR-ROTATED-KEY" \
  -e APP_PASSWORD="local-test" \
  lead-investor-map
# open http://localhost:8501
```

---

## Cost control

- Set a monthly spend limit on the Anthropic key.
- Keep `APP_PASSWORD` set, and share it only with people who should be spending the
  budget.
- For bulk or experimental runs, use the CLI with `--no-llm`: the tiering, ranking,
  sequencing and one-page PDF all work with zero API spend.
- Rotate the key if the URL or the password is ever shared more widely than intended.
