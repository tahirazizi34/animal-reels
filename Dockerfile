FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline code
COPY pipeline/ .

# Create output directories
RUN mkdir -p output test_images test_audio test_output

# Default command — runs the scheduler
CMD ["python", "scheduler.py"]
