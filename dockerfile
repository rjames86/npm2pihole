FROM python:3.11-alpine
RUN apk add --no-cache openssh-client docker-cli
WORKDIR /app
COPY *.py /app/
CMD python main.py
