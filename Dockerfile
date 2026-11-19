FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg MPLCONFIGDIR=/tmp/takt-matplotlib
WORKDIR /app
COPY requirements.txt .
RUN pip install --disable-pip-version-check --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 takt \
    && mkdir -p /app/data && chown takt:takt /app/data
COPY *.py ./
COPY dist/ dist/
USER takt
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/api/health', timeout=3).close()"
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8765"]
