#!/bin/bash
# Deploy C2 to Vercel
# Usage: ./deploy.sh [project-name]

set -e

PROJECT_NAME="${1:-shadow-c2}"
echo "[*] Deploying Shadow C2 to Vercel..."
echo "[*] Project: $PROJECT_NAME"

# Check vercel CLI
if ! command -v vercel &> /dev/null; then
    echo "[*] Installing Vercel CLI..."
    npm install -g vercel
fi

# Login (if not already)
echo "[*] Login to Vercel..."
vercel login

# Deploy
echo "[*] Deploying..."
vercel --prod --yes -n "$PROJECT_NAME"

echo ""
echo "[+] Deployed! Your C2 URL:"
echo "    https://${PROJECT_NAME}.vercel.app"
echo ""
echo "[+] API Endpoints:"
echo "    GET  /                    — Health check"
echo "    POST /?route=checkin      — Agent checkin"
echo "    POST /?route=result       — Task result"
echo "    POST /?route=agents       — List agents"
echo "    POST /?route=task         — Create task"
echo "    POST /?route=stats        — Statistics"
echo ""
echo "[+] Update agent_http.py C2_URL to:"
echo '    C2_URL = "https://'${PROJECT_NAME}'.vercel.app"'
