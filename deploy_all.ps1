# PowerShell script to deploy Strolid Meetings frontend to Firebase and backend to Cloud Run

$ErrorActionPreference = "Stop"

Write-Host "==============================================" -ForegroundColor Green
Write-Host "Starting Strolid Meetings Deployment" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

# Step 1: Build the Next.js Frontend
Write-Host "`n[1/3] Building Next.js Frontend..." -ForegroundColor Cyan
Push-Location frontend
try {
    npm run build
} finally {
    Pop-Location
}

# Step 2: Deploy Frontend to Firebase Hosting
Write-Host "`n[2/3] Deploying Frontend to Firebase..." -ForegroundColor Cyan
Push-Location frontend
try {
    npx firebase-tools deploy --only hosting,firestore --project meeting-analysis-6c116
} finally {
    Pop-Location
}

# Step 3: Deploy Chatbot API to Google Cloud Run
Write-Host "`n[3/3] Deploying Chatbot Backend to Cloud Run..." -ForegroundColor Cyan
# Deploying to project meeting-analysis-6c116 where Firebase rewrite is routed
gcloud run deploy chatbot-api `
    --source . `
    --region us-central1 `
    --project meeting-analysis-6c116 `
    --allow-unauthenticated

Write-Host "`n==============================================" -ForegroundColor Green
Write-Host "Deployment Completed Successfully!" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
