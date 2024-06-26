# Stage 0 - Create from python:3.12-slim-bookworm image
# FROM python:3.12-slim-bookworm as stage0
FROM python:3.12-slim-bookworm
RUN apt update && apt install -y python3-venv

# Stage 1 - Copy Generate code
# FROM stage0 as stage1
RUN /bin/mkdir /data
COPY . /app

# Stage 2 - Install dependencies
# FROM stage1 as stage2
RUN /usr/local/bin/python3 -m venv /app/env
RUN /app/env/bin/pip install -r /app/requirements.txt

# Stage 3 - Execute code
# FROM stage2 as stage3
LABEL version="0.1" \
    description="Containerized Generate: Uploader"
ENTRYPOINT [ "/app/env/bin/python3", "/app/uploader/run_uploader.py" ]