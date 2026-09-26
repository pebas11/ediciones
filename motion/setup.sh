#!/usr/bin/env bash
# Instala las dependencias del motor de motion graphics (idempotente; lo corre el hook SessionStart).
set -e
cd "$(dirname "$0")"
if [ ! -d node_modules/gsap ]; then npm install --no-audit --no-fund --silent >/dev/null 2>&1; fi
[ -d node_modules/playwright ] || npm install --no-save playwright@1.56.1 --silent >/dev/null 2>&1
python3 -c "import imageio_ffmpeg, numpy" 2>/dev/null || pip install -q imageio-ffmpeg numpy pillow >/dev/null 2>&1
echo "motion: dependencias listas"
