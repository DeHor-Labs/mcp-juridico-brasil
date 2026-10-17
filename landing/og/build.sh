#!/bin/sh
# Gera og.png (1200x630) e apple-touch-icon.png (180x180) a partir dos HTML desta pasta.
set -e
cd "$(dirname "$0")"
npx -y playwright@1 screenshot --viewport-size=1200,630 "file://$PWD/og.html" ../og.png
npx -y playwright@1 screenshot --viewport-size=180,180 "file://$PWD/icon.html" ../apple-touch-icon.png
