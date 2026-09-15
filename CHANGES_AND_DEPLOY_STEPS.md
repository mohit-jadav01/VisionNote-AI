# VisionNote AI — Fix Notes & Deploy Steps

## What was actually broken

Two failures were chained together in `backend/app/core/audio.py`:

1. **Real cause:** the YouTube cookies stored on Render (`YT_COOKIES_FILE`) were
   expired/rotated, so YouTube's bot-check rejected the download
   (`Sign in to confirm you're not a bot`).
2. **What you actually saw on screen:** `yt-dlp` tries to write the cookie
   jar back to the same path when it closes. Render **Secret Files** are
   mounted **read-only** at runtime, so that write crashed with
   `OSError: [Errno 30] Read-only file system: '/etc/secrets/cookies.txt'`,
   which then overwrote/masked the real error message in the UI.

(Separately, the earlier 404s in your log were just a session started right
before a Render redeploy — the in-memory session store got wiped on
restart. Not a bug, just an ephemeral-instance timing artifact — a retry
after the redeploy works fine, as your own log shows.)

## What I changed (code — already applied in this zip)

`backend/app/core/audio.py`:
- Copies `YT_COOKIES_FILE` to a writable per-session temp path before
  handing it to `yt-dlp`, instead of pointing `yt-dlp` at the read-only
  Render secret path directly. **This removes the crash.**
- Added `_friendly_download_error()` so bot-check / 403 / stale-cookie
  failures now surface a clear, actionable message instead of a raw
  Python traceback string.

No other files were touched. This is a drop-in replacement for your
existing `backend/` folder.

## Steps YOU still need to do (outside the code — I can't do these for you)

These are the actual reason downloads are failing — the code fix above
only stops the *crash*, it doesn't make expired cookies valid again.

1. **Re-export fresh YouTube cookies**
   - Log into YouTube in a normal browser (use an account you're fine
     using for this — not your primary personal one).
   - Install a "Get cookies.txt" browser extension (e.g. *Get
     cookies.txt LOCALLY* for Chrome/Firefox).
   - Visit youtube.com while logged in, export cookies in **Netscape
     format** as `cookies.txt`.

2. **Upload it to Render as a Secret File**
   - Render Dashboard → your backend service → **Environment** →
     **Secret Files** → Add: filename `cookies.txt`, paste the file
     contents.
   - Confirm env var `YT_COOKIES_FILE=/etc/secrets/cookies.txt` is set
     under **Environment Variables** (add it if missing).

3. **Redeploy the backend**
   - Push this fixed `backend/` folder to your connected GitHub repo (or
     manually redeploy if you deploy from a zip), then trigger **Manual
     Deploy → Deploy latest commit** on Render.

4. **Re-test**
   - Hit your Render backend URL + `/health` (or `/`) to confirm it's up.
   - From the live Netlify frontend, submit the same YouTube link again.
   - Watch Render's **Logs** tab live — you should see
     `Using YouTube cookies file for authenticated download` followed by
     a successful download, not the 403/read-only errors.

5. **Ongoing maintenance (important)**
   - YouTube rotates/expires these cookies periodically (this is *why*
     it broke in the first place). Expect to repeat step 1–3 every few
     weeks, or whenever downloads start failing with a bot-check message
     again — the improved error message will now tell you plainly when
     that's the cause instead of showing a confusing filesystem error.

6. **Double-check CORS/env parity**
   - Confirm `CORS_ORIGINS` on Render includes your exact Netlify URL
     (e.g. `https://your-site.netlify.app`), and that the frontend's
     `js/api.js` / `Fronted/js/*.js` point at your Render backend URL
     (not `localhost`). Neither of these caused today's error, but
     they're common reasons a "fixed" backend still looks broken from
     the live frontend — worth a quick check while you're redeploying.
