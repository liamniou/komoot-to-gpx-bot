# Stage 1: build Rust komootgpx (for public smarttour/tour URLs)
FROM rust:1.99.0-slim-bookworm AS rust
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN cargo install --git https://github.com/cdown/komootgpx

# Stage 2: Python bot + both komootgpx tools
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
# Rust binary as komootgpx-rust to avoid clashing with Python komootgpx script
COPY --from=rust /usr/local/cargo/bin/komootgpx /usr/local/bin/komootgpx-rust

COPY main.py /app
CMD ["python", "main.py"]
