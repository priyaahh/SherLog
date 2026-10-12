# SherLog Production Deployment Guide (100% Free Tier)

This guide documents the end-to-end steps to deploy the complete SherLog incident management & root cause analysis platform using free tier cloud services:

| Component | Technology | Free Host | Configuration Artifact |
| :--- | :--- | :--- | :--- |
| **Frontend** | Vite + React SPA | [Vercel](https://vercel.com) | [`frontend/vercel.json`](file:///c:/Users/priya/OneDrive/Desktop/SherLog/frontend/vercel.json) |
| **Backend API** | FastAPI + Motor | [Render](https://render.com) Web Service | [`render.yaml`](file:///c:/Users/priya/OneDrive/Desktop/SherLog/render.yaml) (`rootDir: backend`) |
| **AI Service** | Flask + LangGraph + Gemini | [Render](https://render.com) Web Service | [`render.yaml`](file:///c:/Users/priya/OneDrive/Desktop/SherLog/render.yaml) (`rootDir: ai-service`) |
| **Database** | MongoDB 7.0+ | [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) | Shared M0 Free Cluster |

---

## Complete Environment Variables Reference

### 1. Render - Backend Service (`sherlog-backend`)
Set these in the **Environment** tab of the `sherlog-backend` service on Render:

| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `MONGODB_URL` | MongoDB Atlas SRV connection string with credentials | `mongodb+srv://user:pass@cluster0.mongodb.net/?retryWrites=true&w=majority` |
| `DATABASE_NAME` | Database name for SherLog collections | `sherlog` |
| `AI_SERVICE_URL` | Public URL of the deployed AI service on Render | `https://sherlog-ai-service.onrender.com` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins (local dev + Vercel) | `http://localhost:5173,https://sherlog-frontend.vercel.app` |
| `PYTHON_VERSION` | Supported Python version on Render | `3.11.9` |

### 2. Render - AI Service (`sherlog-ai-service`)
Set these in the **Environment** tab of the `sherlog-ai-service` service on Render:

| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Google Gemini API key for LangGraph agents | `AIzaSy...` |
| `PORT` | Container port (already specified in Dockerfile) | `5000` |

### 3. Vercel - Frontend Project (`sherlog-frontend`)
Set this in the **Environment Variables** section of the Vercel project:

| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | Base URL of the deployed FastAPI backend (no trailing slash) | `https://sherlog-backend.onrender.com` |

---

## Step-by-Step Deployment Instructions

### Step 1: MongoDB Atlas Network Access Configuration

Render free web services run in shared container clusters where outbound IP addresses are dynamic and change on restarts. You must allow traffic from anywhere:

1. Log in to [MongoDB Atlas](https://cloud.mongodb.com/).
2. In the left navigation, go to **Security** → **Network Access**.
3. Click **+ Add IP Address**.
4. Select **ALLOW ACCESS FROM ANYWHERE** (`0.0.0.0/0`).
5. Set comment: `Render Free Web Services` and click **Confirm**.
6. In **Security** → **Database Access**, verify your database user has `readWriteAnyDatabase` or read/write permissions on the `sherlog` database.
7. Go to **Deployments** → **Database** → Click **Connect** → **Drivers** (Python 3.12+).
8. Copy the connection string (replace `<password>` with your database user password).

---

### Step 2: Deploy AI Service to Render

1. Sign up or log into [Render](https://dashboard.render.com/).
2. Click **New +** → **Web Service**.
3. Select **Build and deploy from a Git repository** and connect `priyaahh/SherLog`.
4. Configure the service:
   - **Name**: `sherlog-ai-service`
   - **Region**: Oregon (or your preferred region)
   - **Branch**: `main`
   - **Root Directory**: `ai-service`
   - **Runtime**: **Docker** (Render will detect `ai-service/Dockerfile`)
   - **Instance Type**: **Free**
5. Expand **Advanced** → **Add Environment Variable**:
   - `PORT` = `5000`
   - `GOOGLE_API_KEY` = `<your-gemini-api-key>`
6. Set **Health Check Path**: `/health`
7. Click **Create Web Service**.
8. Wait for build to complete. Note your assigned service URL:
   `https://sherlog-ai-service.onrender.com`
9. Test in browser:
   `https://sherlog-ai-service.onrender.com/health` should return `{"status": "healthy"}`.

---

### Step 3: Deploy FastAPI Backend to Render

1. On the Render Dashboard, click **New +** → **Web Service**.
2. Select the same Git repository (`priyaahh/SherLog`).
3. Configure the service:
   - **Name**: `sherlog-backend`
   - **Region**: Same region as AI Service (e.g. Oregon)
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: **Python 3**
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: **Free**
4. Expand **Advanced** → **Add Environment Variables**:
   - `PYTHON_VERSION` = `3.11.9`
   - `MONGODB_URL` = `<your-mongodb-atlas-srv-url>`
   - `DATABASE_NAME` = `sherlog`
   - `AI_SERVICE_URL` = `https://sherlog-ai-service.onrender.com`
   - `CORS_ORIGINS` = `http://localhost:5173,https://localhost:3000` *(we will add the Vercel domain in Step 5)*
5. Set **Health Check Path**: `/health`
6. Click **Create Web Service**.
7. Wait for build and startup logs to succeed:
   `Connected to MongoDB at <host>`
8. Note your assigned backend URL:
   `https://sherlog-backend.onrender.com`
9. Test in browser:
   `https://sherlog-backend.onrender.com/health` should return `{"status": "healthy", "database": "connected"}`.

---

### Step 4: Deploy Frontend to Vercel

1. Sign up or log into [Vercel](https://vercel.com/).
2. On your Vercel Dashboard, click **Add New...** → **Project**.
3. Import the repository `priyaahh/SherLog`.
4. Configure the Project:
   - **Framework Preset**: `Vite` (auto-detected)
   - **Root Directory**: Click **Edit** and choose `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
5. Expand **Environment Variables**:
   - **Key**: `VITE_API_BASE_URL`
   - **Value**: `https://sherlog-backend.onrender.com` *(your Render backend URL from Step 3, without trailing slash)*
6. Click **Deploy**.
7. In ~30-45 seconds, the static deployment will be live at a domain like:
   `https://sherlog-frontend.vercel.app`

> [!NOTE]
> Single-Page App (SPA) routing is handled automatically by [`frontend/vercel.json`](file:///c:/Users/priya/OneDrive/Desktop/SherLog/frontend/vercel.json), which rewrites all incoming routes (`/incidents/:id`, `/incidents/new`, `/incidents/:id/report`) to `index.html`.

---

### Step 5: Final Wiring (Update CORS on Render Backend)

Now that you have your live Vercel URL:

1. Return to the [Render Dashboard](https://dashboard.render.com/).
2. Open `sherlog-backend` → **Environment**.
3. Update `CORS_ORIGINS` to include your Vercel domain:
   ```
   http://localhost:5173,https://sherlog-frontend.vercel.app
   ```
4. Click **Save Changes**. Render will automatically redeploy the backend with the updated allowed origin.

---

### Step 6: Verify End-to-End Production Workflow

1. Open your live Vercel frontend URL in a browser.
2. Confirm the header displays:
   `sherlog:~$ ./incident-ops` and `● API: ONLINE`.
3. Click **`[+ NEW INCIDENT]`** and create a test incident.
4. On the incident detail view, select a `.log` or `.txt` file and upload it.
5. Click **`TRIGGER INVESTIGATION`**:
   - Status badge shows `[IN_PROGRESS]` with the blinking indicator.
   - Frontend auto-polls the backend every 5 seconds.
   - Backend calls the AI service on Render, running the multi-agent LangGraph pipeline with Gemini.
   - Upon completion, status changes to `[INVESTIGATED]`.
6. Click **`[!] VIEW RCA REPORT`**:
   - Review root cause analysis, risk metrics, actionable recommendations, and parsed anomaly sample lines.
7. Click **`RESOLVE INCIDENT`** and confirm status transitions to `[RESOLVED]`.

---

### Important Free Tier Notes

> [!WARNING]
> **Render Free Tier Spin-Down**:
> Render free web services automatically sleep after 15 minutes of inactivity. The first request after a period of dormancy will spin up the container, taking ~30–50 seconds. Subsequent requests will respond instantly.
>
> To avoid initial request timeouts when testing, ping both `/health` endpoints once before triggering workflows in the UI:
> - `https://sherlog-ai-service.onrender.com/health`
> - `https://sherlog-backend.onrender.com/health`
