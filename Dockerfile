# Use Alpine Linux for a minimal footprint
FROM python:3.12-alpine

# Set the working directory
WORKDIR /app

# Upgrade system packages to patch OS-level CVEs
RUN apk update && apk upgrade --no-cache

# Copy and install dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
RUN /bin/mkdir /data
COPY . /app

# Stage 3 - Execute code
# FROM stage2 as stage3
LABEL version="0.1" \
    description="Containerized Generate: Uploader"
ENTRYPOINT [ "python3", "/app/uploader/run_uploader.py" ]