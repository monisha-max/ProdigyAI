FROM python:3.12-slim

WORKDIR /app

# Install toolbox binary
ENV TOOLBOX_VERSION=0.23.0
RUN apt-get update && apt-get install -y curl && \
    curl -O https://storage.googleapis.com/genai-toolbox/v${TOOLBOX_VERSION}/linux/amd64/toolbox && \
    chmod +x toolbox && \
    apt-get remove -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Start script: launch toolbox, then FastAPI
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080
CMD ["./start.sh"]
