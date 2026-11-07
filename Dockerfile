# PharmaFind website - built and run by Render (render.yaml), Hugging Face Spaces or any Docker host.
FROM python:3.13-slim

# Small system library that OpenCV can need
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face runs the app as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PHARMAFIND_PRODUCTION=1 \
    MALLOC_ARENA_MAX=2
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt "gunicorn>=23"

COPY --chown=user . .

# Prepare the database and the photo index now, so the site starts fast.
# (The secret key is removed so every running copy makes its own.)
RUN python seed.py && python prepare.py && rm -f instance/secret_key

EXPOSE 7860
CMD ["sh", "start.sh"]
