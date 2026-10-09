FROM 10.47.0.221:5000/python-base:latest
WORKDIR /app
ADD table_service .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]