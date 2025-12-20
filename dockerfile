FROM python:3.11-alpine
RUN apk add --no-cache openssh-client
WORKDIR /app
COPY main.py /app
CMD python main.py
