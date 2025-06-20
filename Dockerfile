FROM python:3.12-slim

# Instalar dependencias ANTES de PyAudio
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    libasound2-dev \
    gcc \
    g++ \
    make \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Instalar PyAudio por separado primero
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pyaudio==0.2.14 && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "nova_sonic_webhook:app", "--host", "0.0.0.0", "--port", "8000"]
