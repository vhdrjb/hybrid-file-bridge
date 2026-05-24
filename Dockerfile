FROM python:3.11-slim

# Install aria2 and ffmpeg from Debian repos
RUN apt-get update && \
    apt-get install -y --no-install-recommends aria2 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install rar from RARLAB (not available in Debian repos)
RUN apt-get update && \
    apt-get install -y --no-install-recommends wget unzip && \
    wget -q https://www.rarlab.com/rar/rarlinux-x64-7.1.3.tar.gz -O /tmp/rar.tar.gz && \
    tar -xzf /tmp/rar.tar.gz -C /tmp && \
    cp /tmp/rar/rar /usr/local/bin/ && \
    cp /tmp/rar/unrar /usr/local/bin/ && \
    chmod +x /usr/local/bin/rar /usr/local/bin/unrar && \
    rm -rf /tmp/rar /tmp/rar.tar.gz && \
    apt-get purge -y --auto-remove wget unzip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY tools/ ./tools/
RUN mkdir -p downloads

CMD ["python", "bot.py"]
