# Dr Shantanu Samanta©️ — Smart Diet Clinic

Password-protected clinical tool. Generates personalised, regionally appropriate diet
charts from patient details and lab reports, and analyses meal photos. Charts download as
a print-ready A4 PDF.

---

## What you need first

- A **GitHub** account — free, at github.com
- A **Streamlit Community Cloud** account — free, at share.streamlit.io (sign in with GitHub)
- A **Gemini API key** — free, at https://aistudio.google.com/apikey

---

## Deploy — 4 steps, about 8 minutes

### Step 1 — Get your Gemini API key

1. Open **https://aistudio.google.com/apikey**
2. Sign in → **Create API key** → **Create API key in new project**
3. Copy it. It begins with `AIza…`

Treat it like a password. It's billable, and it should never appear in a file you upload.

### Step 2 — Put the code on GitHub

1. Go to **github.com** → green **New** button (or https://github.com/new)
2. Repository name: `diet-clinic` · set it to **Private** · click **Create repository**
3. On the next screen click **uploading an existing file**
4. Drag in **every file from this folder**, including the hidden `.streamlit` folder
5. Click **Commit changes**

> On a Mac, press **Cmd + Shift + .** in Finder to see the `.streamlit` folder.
> If it still won't upload, you can skip it — the app runs fine without it, just with
> Streamlit's default colours instead of the clinic blue.

### Step 3 — Deploy on Streamlit

1. Go to **https://share.streamlit.io** → sign in with GitHub
2. Click **Create app** → **Deploy a public app from GitHub**
3. Repository: your `diet-clinic` · Branch: `main` · Main file path: **`app.py`**
4. Click **Advanced settings** → in the **Secrets** box paste exactly this, with your
   own values:

```toml
GEMINI_API_KEY = "AIza...your-real-key..."
APP_PASSWORD = "your-clinic-password"
```

5. Click **Deploy**

First build takes 3–5 minutes — it's installing the fonts needed for Bengali, Hindi,
Tamil and the other Indian scripts. Later restarts are quick.

### Step 4 — Test it

1. Your app opens at `https://your-app-name.streamlit.app`
2. Try a wrong password → *"Incorrect password."*
3. Enter your real password → you're in
4. Generate a chart for a test patient
5. **Download the PDF and check the local-language names.** If you see empty boxes
   instead of Bengali or Hindi text, see *Troubleshooting* below.

---

## Making it properly private (recommended)

The password gate stops casual visitors, but the app URL is still public. For real
access control:

**Manage app → Settings → Sharing** → set the app to **private**, then invite staff by
email address. Only those people can open it at all — a much stronger gate than a shared
password, and you can revoke one person without changing anything for everyone else.

Keep `APP_PASSWORD` set either way; it's a useful second layer on a shared clinic computer.

---

## Changing the password later

**Manage app → Settings → Secrets** → edit the value → **Save**. The app restarts on its
own within a few seconds. No redeploy needed.

---

## Everyday notes

**Nothing is stored.** Patient details live only in the open browser session. Close the
tab and they're gone. Download each chart before you navigate away.

**Sign out** is in the left sidebar — worth using on a shared computer.

**The app sleeps** after about a week with no visitors. The next person to open it waits
roughly 30 seconds while it wakes. Daily clinic use means you'll never see this.

**Cost.** Streamlit Community Cloud is free. Gemini's free tier covers normal clinic
volume; if you hit quota errors, add billing to the Google Cloud project behind your key.

---

## Troubleshooting

**"Not configured yet" on the sign-in screen**
`APP_PASSWORD` is missing from Secrets. Check the spelling — all capitals with an
underscore — and that it's inside quotes.

**"GEMINI_API_KEY is not set"**
Same fix, for the other key.

**"AI service error (400): API key not valid"**
The key was copied incompletely, or its Google project lacks Generative Language API
access. Create a fresh key in AI Studio and replace it in Secrets.

**Local-language names show as empty boxes (□□□) in the PDF**
The Noto fonts didn't install. Confirm `packages.txt` made it into your GitHub repo, then
**Manage app → Reboot app**. If the boxes persist, use the **Download HTML** button
instead — your browser has its own fonts and will render every script correctly, and it
prints to A4 just as well.

**The PDF button is missing, replaced by a warning**
WeasyPrint couldn't start. Check `packages.txt` uploaded correctly and reboot. The HTML
download always works regardless.

**"The AI service is busy or rate-limited (429)"**
Gemini's free tier throttles requests per minute. Wait a minute and try again.

**Chart generation keeps failing**
Usually an unreadable lab report photo. Generate without attachments to confirm the rest
works, then re-add reports one at a time.

---

## Running locally (optional)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill in real values
streamlit run app.py
```

On macOS, PDF generation also needs `brew install pango`. Without it the app still runs —
you just get the HTML download instead.

---

## What's in each file

| File | What it does |
| --- | --- |
| `app.py` | The app itself — sign-in, intake form, meal tracker, downloads |
| `ai.py` | Talks to Gemini; keeps the API key server-side, retries on transient errors |
| `render.py` | Builds the A4 chart as HTML, then converts it to PDF |
| `requirements.txt` | Python packages Streamlit installs |
| `packages.txt` | System packages — PDF engine and the Indian-language fonts |
| `.streamlit/config.toml` | Clinic colour theme |
| `.streamlit/secrets.toml.example` | Template for local secrets — never commit the real one |

---

## Clinical caution

Every chart is AI-generated and labelled indicative. Calorie figures, the BMI reading and
any lab interpretation are model estimates, not verified calculations. Read each chart
before it reaches a patient — especially the numbers, and especially for anyone with
diabetes, renal impairment, or on a restricted diet.
