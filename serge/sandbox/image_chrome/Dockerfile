# Le vrai Chrome de Serge : un Chromium normal (pas « headless »), sur un
# écran virtuel, qu'un humain peut voir et piloter depuis Mission Control.
# Construite par Serge au premier usage (serge/sandbox/chrome.py).
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium xvfb openbox x11vnc novnc websockify socat \
        ca-certificates fonts-dejavu-core fonts-liberation \
        fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 chrome \
    && install -d -o chrome -g chrome /home/chrome/profil
COPY demarrer.sh /usr/local/bin/demarrer.sh
USER chrome
WORKDIR /home/chrome
EXPOSE 9223 6080
ENTRYPOINT ["/bin/sh", "/usr/local/bin/demarrer.sh"]
