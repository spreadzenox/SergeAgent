# L'atelier vidéo de Serge : de quoi monter, contrôler et rendre une vidéo
# verticale avec HyperFrames, aligner la voix sur le texte, et capturer le
# site d'un produit. Construite par Serge au premier usage du profil
# « video » (serge/sandbox/images.py), une fois par version de ces fichiers.
FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    CONTAINER=true \
    HYPERFRAMES_NO_TELEMETRY=1 \
    HF_HOME=/opt/atelier/modeles \
    HF_HUB_DISABLE_XET=1 \
    NODE_PATH=/usr/local/lib/node_modules \
    PATH=/opt/atelier/bin:$PATH

# Ce qu'il faut à Chrome sans écran, et les polices de secours.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg python3-venv ca-certificates curl \
        libgbm1 libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 \
        libxdamage1 libxrandr2 libcups2 libasound2 libpangocairo-1.0-0 \
        libxshmfence1 libgtk-3-0 \
        fonts-liberation fonts-noto-color-emoji fonts-dejavu-core fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

# Le moteur, à une version figée : une vidéo se refait à l'identique.
RUN npm install -g hyperframes@0.9.104 puppeteer-core@25.19.0 \
    && hyperframes browser ensure

# L'alignement de la voix sur le texte (modèle sous licence Apache 2.0).
RUN python3 -m venv /opt/atelier/venv \
    && /opt/atelier/venv/bin/pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1 torchaudio==2.5.1 \
    && /opt/atelier/venv/bin/pip install --no-cache-dir transformers==4.46.3 numpy==2.1.3

COPY bin /opt/atelier/bin
COPY sons /opt/atelier/sons
COPY exemple /opt/atelier/exemple
RUN chmod +x /opt/atelier/bin/* && aligner --prechauffe

WORKDIR /work
