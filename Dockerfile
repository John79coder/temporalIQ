ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to maximize Docker layer caching
COPY requirements.txt .

# Upgrade pip
RUN pip install --upgrade pip

# Install the CPU-only build of PyTorch
ARG TORCH_VERSION=2.7.1
RUN pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==${TORCH_VERSION}

# Install the remainder of the Python dependencies.
# torch is already installed, so pip should satisfy that requirement
# without downloading the CUDA-enabled build.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY . .

# Download AI models during image build
RUN python download_models.py

EXPOSE 5000

CMD ["python", "main.py"]