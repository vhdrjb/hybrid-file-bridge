FROM python:3.11-slim

# Enable non-free repo (needed for rar) and install system tools
RUN sed -i 's/main$/main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends rar aria2 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY tools/ ./tools/
RUN mkdir -p downloads

CMD ["python", "bot.py"]
