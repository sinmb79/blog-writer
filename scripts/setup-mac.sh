#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "========================================"
echo " Blog Engine Setup (macOS)"
echo "========================================"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Install Python 3.11+ first."
  exit 1
fi

PYVER=$(python3 - <<'INNER'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
INNER
)
echo "[INFO] Using python3 ($PYVER): $(command -v python3)"

if [ ! -d venv ]; then
  echo "[INFO] Creating virtualenv..."
  python3 -m venv venv
else
  echo "[INFO] Reusing existing venv"
fi

source venv/bin/activate
python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "[OK] .env file created. Please fill in your API keys: .env"
fi

echo "[INFO] Creating data/config/assets/input directories..."
mkdir -p \
  data/topics data/collected data/discarded data/pending_review data/published \
  data/analytics data/images data/drafts data/originals data/outputs \
  data/assist/sessions data/assist/inbox data/novels \
  logs config/novels data/shorts/scripts data/shorts/clips \
  data/shorts/tts data/shorts/captions data/shorts/rendered \
  data/shorts/published assets/characters/zero/expressions \
  assets/characters/zero/poses assets/characters/bao/expressions \
  assets/characters/bao/poses assets/characters/bao/scarves \
  assets/backgrounds/fourth_path assets/backgrounds/tech_blog assets/bgm \
  input/images input/videos input/scripts input/audio input/_processed \
  templates/shorts

echo "[INFO] Downloading fonts..."
python scripts/download_fonts.py

echo
echo "========================================"
echo " Setup Complete!"
echo "========================================"
echo
echo "Next steps:"
echo "1. Open .env and fill in all API keys"
echo "2. Run: python scripts/get_token.py"
echo "   (Blogger + Search Console + YouTube OAuth)"
echo "3. Update BLOG_MAIN_ID in .env with your Blogger blog ID"
echo "4. Start scheduler: python bots/scheduler.py"
echo "5. Start dashboard backend: python -m dashboard.backend.server"
echo "6. If frontend is needed, run it separately from dashboard/frontend"
echo
echo "NOTE: Windows Task Scheduler registration from setup.bat is intentionally skipped on macOS."
