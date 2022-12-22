FROM python:3.11

RUN apt-get update -yq \
    && apt-get -yq install curl wget \
    && curl -L https://deb.nodesource.com/setup_18.x | bash \
    && apt-get update -yq \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install ./google-chrome-stable_current_amd64.deb -yq \
    && apt-get install -yq \
        nodejs

RUN npm install -g lighthouse

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

EXPOSE 1338

ENTRYPOINT [ "python", "./src/report.py" ]