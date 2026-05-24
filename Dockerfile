FROM python:3.11-slim

# Enable multiverse and install rar + aria2
RUN echo "deb http://archive.ubuntu.com/ubuntu jammy multiverse" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends rar aria2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY tools/ ./tools/
RUN mkdir -p downloads

CMD ["python", "bot.py"]
