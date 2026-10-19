# Cloud Video Production Studio — one image for Codespaces, CI, and GPU render workers.
# CPU build:  docker build -t video-studio .
# GPU build:  docker build --build-arg BASE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 -t video-studio:gpu .
ARG BASE=python:3.12-slim-bookworm
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-noto-cjk fonts-noto-color-emoji fontconfig git curl ca-certificates \
        $(command -v python3 >/dev/null || echo python3 python3-pip) \
    && rm -rf /var/lib/apt/lists/* && fc-cache -f

WORKDIR /studio
COPY requirements.txt pyproject.toml ./
RUN python3 -m pip install -r requirements.txt
COPY . .
RUN python3 -m pip install -e . && studio audit --offline > /dev/null

CMD ["studio", "--help"]
