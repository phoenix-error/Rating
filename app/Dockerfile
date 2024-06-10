# syntax=docker/dockerfile:1
FROM python:3.9-slim

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Expose the port that the application listens on.
EXPOSE 8080

COPY . .

# Run the application.
CMD ["python", "rating_app.py"]
