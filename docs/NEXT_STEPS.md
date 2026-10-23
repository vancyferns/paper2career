# Paper2Career - Next Steps & Deployment Guide

This guide outlines the concrete next steps to take Paper2Career from local development to production on **Appwrite Cloud** and configure automated daily ingestion.

---

## 1. Appwrite Cloud Onboarding (Immediate)

### A. Create Project & API Key
1. Sign in to [Appwrite Cloud](https://cloud.appwrite.io).
2. Create a new project (e.g., `Paper2Career`).
3. Note your **Project ID** and **Endpoint** (typically `https://fra.cloud.appwrite.io/v1` for Frankfurt, or your chosen region).
4. Go to **Project Settings → API Keys → Create API Key**:
   - **Name**: `Paper2Career Worker Key`
   - **Scopes**:
     - `databases.read`, `databases.write`
     - `tables.read`, `tables.write`
     - `columns.read`, `columns.write`
     - `indexes.read`, `indexes.write`
     - `rows.read`, `rows.write`
     - `buckets.read`, `buckets.write`
     - `files.read`, `files.write`
     - `teams.read`, `teams.write`
5. Go to **Auth → Settings** and ensure **Email/Password** is enabled.
6. Go to **Auth → Platforms → Add Platform → Web App**:
   - Name: `Local Development`
   - Hostname: `localhost`

---

### B. Configure Local Environment Files

1. Open [`worker/.env`](file:///d:/paper2career/worker/.env):
   ```env
   APPWRITE_ENDPOINT=https://fra.cloud.appwrite.io/v1
   APPWRITE_PROJECT_ID=<your_project_id>
   APPWRITE_API_KEY=<your_api_key>
   APPWRITE_DATABASE_ID=paper2career_db
   AUTO_PUBLISH=true
   ```

2. Open [`frontend/.env.local`](file:///d:/paper2career/frontend/.env.local):
   ```env
   VITE_APPWRITE_ENDPOINT=https://fra.cloud.appwrite.io/v1
   VITE_APPWRITE_PROJECT_ID=<your_project_id>
   VITE_APPWRITE_DATABASE_ID=paper2career_db
   ```

---

### C. Provision Schema & Seed Data

Run the following commands in PowerShell from the project root:

```powershell
$env:PYTHONPATH='worker'

# 1. Verify credentials and connectivity
worker\.venv\Scripts\python -m paper2career check-appwrite

# 2. Provision TablesDB tables, indexes, storage bucket, and reviewers team
worker\.venv\Scripts\python -m paper2career setup

# 3. Seed existing curated jobs (220+ verified ads) and JPEG crops to Appwrite
worker\.venv\Scripts\python -m paper2career sync-to-appwrite
```

Once completed:
- Refresh your Appwrite Cloud console:
  - **Databases → paper2career_db**: You will see all 5 tables populated (`editions`, `jobs`, `job_appearances`, `job_revisions`, `ingestion_runs`).
  - **Storage → ad_crops**: All classified ad snippet crops are uploaded.
- Refresh `http://localhost:5173/`: Your frontend now reads live from Appwrite TablesDB.

---

## 2. Deploy the Frontend (Appwrite Sites / Static Host)

### Option A: Deploy on Appwrite Sites
1. Push your repository to GitHub.
2. In the Appwrite Console, navigate to **Sites (Hosting)** and click **Create Site**.
3. Connect your GitHub repository:
   - **Root directory**: `frontend`
   - **Build command**: `npm run build`
   - **Output directory**: `dist`
4. Add Environment Variables:
   - `VITE_APPWRITE_ENDPOINT`: `https://fra.cloud.appwrite.io/v1`
   - `VITE_APPWRITE_PROJECT_ID`: `<your_project_id>`
   - `VITE_APPWRITE_DATABASE_ID`: `paper2career_db`
5. Once deployed, copy your production site domain (e.g. `paper2career.appwrite.global`).
6. In **Auth → Platforms**, add a Web platform for your production domain.

### Option B: Deploy on Cloudflare Pages / Vercel
1. Set framework to **Vite**, build command `npm run build`, output directory `frontend/dist`.
2. Configure the same 3 `VITE_APPWRITE_*` environment variables.
3. Whitelist the deployment domain in Appwrite Web Platforms.

---

## 3. Daily Automated Ingestion Workflow

To ingest newspaper classifieds every morning automatically:

### GitHub Actions (Recommended)
1. Go to your GitHub repository **Settings → Secrets and variables → Actions**.
2. Add the following repository secrets:
   - `APPWRITE_ENDPOINT` (e.g. `https://fra.cloud.appwrite.io/v1`)
   - `APPWRITE_PROJECT_ID`
   - `APPWRITE_API_KEY`
   - `AUTO_PUBLISH` (`true`)
3. The workflow file [`.github/workflows/daily-ingestion.yml`](file:///d:/paper2career/.github/workflows/daily-ingestion.yml) will trigger daily at **06:00, 07:00, 10:00, and 14:00 IST** (00:30, 01:30, 04:30, 08:30 UTC).
4. It downloads that morning's edition, segments classified blocks, runs OCR, auto-publishes jobs, and updates Appwrite without manual intervention.

### Local Windows Task Scheduler Alternative
If you prefer running the worker on a local machine:
- Run [`worker/scripts/daily_run.bat`](file:///d:/paper2career/worker/scripts/daily_run.bat) or [`worker/scripts/daily_run.ps1`](file:///d:/paper2career/worker/scripts/daily_run.ps1) via Windows Task Scheduler every day at 07:00 AM.

---

## 4. Operational & Quality Maintenance

1. **Auto-Publishing vs. Review Queue**:
   - `AUTO_PUBLISH=true` is enabled by default. Newly detected jobs are immediately marked `published` with public read access.
   - The extraction engine filters out contact addressees (e.g. *"Walk-in interview: Apply to Manager..."* is correctly extracted as the advertised teacher/staff role, not "Manager").
   - Disambiguation logic separates 10-digit Indian phone numbers from salary amounts.
2. **Reviewer Overrides (If Needed)**:
   - Access `/#/review` on the frontend.
   - Any team member in the Appwrite `reviewers` team can log in via email/password to edit titles, qualifications, or reject invalid ads.
3. **Ingestion Monitoring**:
   - Access `/#/runs` (linked discreetly in the footer) to view run duration, pages scanned, and ad yield for each publication date.

---

## 5. Future Enhancements Roadmap

- [ ] **Multi-Newspaper Support**: Expand scraper and layout detectors beyond *O Heraldo* to include *The Navhind Times*, *Gomantak Times*, and regional language dailies.
- [ ] **Job Seeker Alerts**: Implement an Appwrite Function triggered on new job insertions to send daily digest notifications via WhatsApp/Telegram based on category or location.
- [ ] **Semantic / AI Search**: Utilize Appwrite Cloud Functions with embedding models to enable natural-language job searches (e.g., *"part-time accounts job near Panaji"*).
