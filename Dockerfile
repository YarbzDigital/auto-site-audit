FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

EXPOSE 1338

ENTRYPOINT [ "python", "report.py" ]