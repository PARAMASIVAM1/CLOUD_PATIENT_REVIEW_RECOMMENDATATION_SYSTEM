# 🚀 Complete Guide: Deploying Healthcare AI Portal to Render

This step-by-step guide explains how to deploy this Flask + Machine Learning + PostgreSQL project to **[Render](https://render.com)** cloud platform.

---

## 📋 Prerequisites
1. **GitHub Account**: [github.com](https://github.com)
2. **Render Account**: [render.com](https://render.com) (Free tier available)
3. **Git**: Installed on your computer

---

## 🛠️ Files Already Configured for Render in Your Project:
We have already prepared and configured all cloud-ready files for you:
* **`render.yaml`**: Render Blueprint configuration for 1-click automatic deployment.
* **`Procfile`**: Specifies `web: gunicorn app:app --workers 2 --timeout 120`.
* **`requirements.txt`**: Includes `gunicorn`, `pg8000`, `Flask`, `pandas`, `scikit-learn`, etc.
* **`db.py`**: Auto-detects cloud `DATABASE_URL` with SSL support for Render PostgreSQL.
* **`init_cloud_db.py`**: Automatically populates all 26,700+ doctors, hospitals, FAQs, schemas, and admin accounts on first cloud run.
* **`.gitignore`**: Prevents unnecessary cache and virtual environment files from being uploaded.

---

## 📌 STEP 1: Push Your Code to GitHub

Open VS Code terminal or PowerShell in your project folder:

```bash
# 1. Initialize git (if not already initialized)
git init

# 2. Stage all files (this includes the new templates, db.py, and cloud configs)
git add .

# 3. Commit your changes
git commit -m "Prepare healthcare project for Render cloud deployment"

# 4. Link to your GitHub repository (replace with your repo URL)
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY_NAME.git

# 5. Push to GitHub
git push -u origin main
```

---

## 🚀 STEP 2: Deploy on Render

You can deploy using **Method A (Easiest - 1 Click Blueprint)** or **Method B (Manual Web Service)**.

---

### 🌟 Method A: 1-Click Blueprint (Recommended)

1. Log in to your **[Render Dashboard](https://dashboard.render.com)**.
2. Click the blue **`New +`** button at the top-right and select **`Blueprint`**.
3. Connect your GitHub account and select your repository.
4. Render will automatically read `render.yaml` from your project and show:
   * **Web Service**: `healthcare-ai-portal` (Python)
   * **Database**: `healthcare-db` (PostgreSQL)
5. Click **`Apply`**.
6. Render will automatically:
   * Provision the PostgreSQL database.
   * Connect `DATABASE_URL`.
   * Install dependencies and run `python init_cloud_db.py` to import all doctors and schemas.
   * Start the web app using `gunicorn`.

---

### 🛠️ Method B: Manual Setup (Step-by-Step)

If you prefer setting it up manually:

#### Part 1: Create the Cloud PostgreSQL Database
1. In Render Dashboard, click **`New +`** &rarr; **`PostgreSQL`**.
2. Set the details:
   * **Name**: `healthcare-db`
   * **Database**: `healthcare_db`
   * **User**: `postgres` (or default)
   * **Region**: Choose the closest region (e.g., Singapore or Frankfurt or Oregon)
   * **Plan**: `Free`
3. Click **`Create Database`**.
4. Once created, scroll down to **Connections** and copy the **`Internal Database URL`** (or **`External Database URL`**).

#### Part 2: Create the Web Service
1. Click **`New +`** &rarr; **`Web Service`**.
2. Select **Build and deploy from a Git repository** &rarr; Choose your repository.
3. Configure the settings:
   * **Name**: `healthcare-ai-portal`
   * **Region**: Same region as your database
   * **Runtime**: `Python 3`
   * **Build Command**: `pip install -r requirements.txt && python init_cloud_db.py`
   * **Start Command**: `gunicorn app:app --workers 2 --timeout 120`
   * **Plan**: `Free`
4. Click **`Advanced`** &rarr; **`Add Environment Variable`**:
   * Key: `DATABASE_URL` | Value: *(Paste the Database URL copied in Part 1)*
   * Key: `HEALTHCARE_SECRET_KEY` | Value: `generate-a-random-secret-key-12345`
   * Key: `PYTHON_VERSION` | Value: `3.11.9`
5. Click **`Create Web Service`**.

---

## 🔑 STEP 3: Default Credentials on Cloud

Once your deployment status turns green (**`Live`**):

* **Web Portal URL**: Click the URL provided by Render (e.g., `https://healthcare-ai-portal.onrender.com`).
* **Default Admin Login**:
  * Email: `admin@healthcare.com`
  * Password: `admin123`
  * Role: `System Admin`
* **Default Patient Login**:
  * Email: `patient@example.com`
  * Password: `password123`
  * Role: `User / Patient`
* **Any Doctor Login**:
  * Email or Name: Any doctor from search (e.g. `drvikrampillai243@hospital.com`)
  * Password: `doctor123`
  * Role: `Doctor`

---

## 💡 Important Tips for Render Free Tier:
1. **Inactivity Sleep**: Render Free tier web services go to sleep after 15 minutes of no visits. The first request after sleep may take ~30–50 seconds to wake up (spin-up). Subsequent requests will be instant.
2. **Logs**: If you encounter any issue, go to the **`Logs`** tab in your Render Web Service dashboard to see live terminal output.
3. **Database Population**: `init_cloud_db.py` runs once during the build process to load the 26,712 doctor records. If you ever want to re-run it, you can open Render's **`Shell`** tab and type `python init_cloud_db.py`.

