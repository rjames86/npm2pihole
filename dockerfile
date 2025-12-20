FROM bash:5.2.37
RUN apk add --no-cache openssh-client jq
WORKDIR /app
COPY main.bash /app
CMD bash main.bash
