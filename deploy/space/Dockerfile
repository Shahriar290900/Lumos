# Lumos on Hugging Face Spaces.
#
# One container: the FastAPI service and the interface it serves. The database
# is Neon and the embedding model is called over HTTP, so this image needs no
# GPU and no model weights — it starts in seconds rather than minutes, which is
# what makes a Space usable for a demo.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

COPY --chown=user requirements-space.txt .
RUN pip install --no-cache-dir --user -r requirements-space.txt

COPY --chown=user apps ./apps
COPY --chown=user services ./services
COPY --chown=user packages ./packages

# Spaces routes to 7860.
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
