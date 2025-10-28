FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN chmod -R a+r /app

EXPOSE 5000

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
ENV PATH="/home/appuser/.local/bin:${PATH}"

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app", "--timeout", "120"]
