FROM python:3.13-alpine@sha256:1a63a53928ce53d2b0baf08092a703f4840ac5dfbd61fd48802dbf48e08c801e
RUN apk add --no-cache ffmpeg && pip install --no-cache-dir Pillow==11.3.0
WORKDIR /app
COPY native/ /app/
USER 1000:1000
CMD ["python3", "-u", "/app/server.py"]
