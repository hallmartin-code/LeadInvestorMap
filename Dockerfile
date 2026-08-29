# Railway builds this image. Everything the app needs is baked in; the API key is not -
# it arrives at runtime as a Railway variable.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8501

# Optional: uncomment to read legacy .ppt decks, which need LibreOffice to convert.
# It adds roughly 450 MB to the image. .pdf and .pptx work without it.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libreoffice-impress fonts-dejavu-core \
#  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first, so editing code does not reinstall the world.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY app.py pyproject.toml README.md ./
COPY .streamlit ./.streamlit
COPY static ./static
COPY sample_data/make_samples.py ./sample_data/make_samples.py

# Outputs are written per request into a temporary directory; this is only a fallback.
RUN mkdir -p /app/output

# Drop root before serving.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

# Railway injects $PORT. One replica: uploads and results live in this process.
CMD ["sh", "-c", "streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.maxUploadSize ${MAX_UPLOAD_MB:-64}"]
