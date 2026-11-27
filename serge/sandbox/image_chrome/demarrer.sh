#!/bin/sh
# Lance l'écran virtuel, son partage pour Mission Control, puis Chromium.
#
# - Xvfb : un écran de 1440 × 900, sans carte graphique ;
# - x11vnc : partage cet écran, seulement dans le conteneur (port 5900) ;
# - websockify : le sert au navigateur de l'humain (noVNC, port 6080),
#   publié sur le serveur seulement, et montré par Mission Control
#   derrière sa connexion ;
# - socat : Chromium n'écoute son port de débogage (CHROME_PORT, 9222 par
#   défaut) que dans le conteneur ; socat le relaie sur CDP_RELAY (9223 par
#   défaut), publié sur le serveur seulement. Les deux ports se règlent
#   pour le réseau partagé du VPN, où le navigateur sans écran garde déjà
#   9222, 9223 et du coup son relais publié (chrome.py).
set -e
export DISPLAY=:1
CHROME_PORT=${CHROME_PORT:-9222}
CDP_RELAY=${CDP_RELAY:-9223}
# Un arrêt brutal laisse ces verrous : ils empêcheraient de redémarrer.
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 "$HOME"/profil/Singleton*
Xvfb :1 -screen 0 1440x900x24 -nolisten tcp &
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -e /tmp/.X11-unix/X1 ] && break
    sleep 0.5
done
openbox &
x11vnc -display :1 -rfbport 5900 -localhost -forever -shared -nopw \
    -quiet -bg
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &
socat TCP-LISTEN:$CDP_RELAY,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:$CHROME_PORT &
exec chromium \
    --no-first-run --no-default-browser-check --no-sandbox \
    --password-store=basic --lang=fr-FR \
    --window-position=0,0 --window-size=1440,900 \
    --user-data-dir="$HOME/profil" \
    --remote-debugging-port=$CHROME_PORT \
    --remote-debugging-address=0.0.0.0 \
    about:blank
