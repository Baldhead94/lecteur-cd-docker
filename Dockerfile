FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends cdparanoia ffmpeg eject cd-discid ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py index.html ./
ENV PORT=8095 CD_DEVICE=/dev/sr0 PYTHONUNBUFFERED=1
EXPOSE 8095
CMD ["python3","-u","app.py"]
