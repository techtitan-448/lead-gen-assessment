# LeadLens — single image serving the Streamlit UI (default) or the FastAPI service.
#   docker build -t leadlens .
#   docker run -p 8501:8501 leadlens                                   # UI
#   docker run -p 8000:8000 leadlens uvicorn api:app --host 0.0.0.0    # API
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libxml2 libxslt1.1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p data && useradd -m app && chown -R app /app
USER app

EXPOSE 8501 8000
HEALTHCHECK CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').status==200 else 1)" || exit 1
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
