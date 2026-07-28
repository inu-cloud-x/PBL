FROM python:3.12-alpine
RUN apk add --no-cache iproute2 nftables
WORKDIR /app
COPY blockchain_daemon.py /app/blockchain_daemon.py
CMD ["python", "/app/blockchain_daemon.py"]
