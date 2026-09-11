#!/bin/bash
# Mockingbird stub-engine entrypoint.
#
# STUB_PROTOCOL=HTTP (default): runs only the Spring Boot / WireMock jar on
#   :8080, exactly as before this file existed.
# STUB_PROTOCOL=HTTPS or BOTH: also starts nginx on :443 terminating TLS
#   (and, when MTLS_ENABLED=true, verifying client certificates) in front of
#   the same unchanged WireMock backend on loopback :8080.
#
# Both processes are supervised here rather than split across two
# containers: the actual deploy path (terraform/stub-ec2) runs a single
# `docker run` per EC2 instance, not an orchestrator that could place a
# sidecar container next to this one, so packaging nginx into the same
# image is what keeps that deploy path a one-container operation. If either
# process dies, this script exits non-zero, which stops the container —
# `docker run --restart unless-stopped` (already set by Terraform) then
# restarts both cleanly rather than leaving a half-working stub running.
set -euo pipefail

CERT_DIR=/etc/nginx/certs
NGINX_PID=""
JAVA_PID=""

term_handler() {
  [ -n "$NGINX_PID" ] && kill -TERM "$NGINX_PID" 2>/dev/null || true
  [ -n "$JAVA_PID" ] && kill -TERM "$JAVA_PID" 2>/dev/null || true
  wait || true
  exit 0
}
trap term_handler TERM INT

if [ "${STUB_PROTOCOL:-HTTP}" != "HTTP" ]; then
  mkdir -p "$CERT_DIR"

  if [ "${TLS_CERT_SOURCE:-AUTO_GENERATED}" = "AUTO_GENERATED" ] && [ ! -f "$CERT_DIR/server.crt.pem" ]; then
    echo "No certificate present — generating a self-signed one for this instance..."
    openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
      -keyout "$CERT_DIR/server.key.pem" \
      -out "$CERT_DIR/server.crt.pem" \
      -subj "/CN=mockingbird-stub/O=Mockingbird" \
      -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
  fi

  if [ ! -f "$CERT_DIR/server.crt.pem" ] || [ ! -f "$CERT_DIR/server.key.pem" ]; then
    echo "FATAL: STUB_PROTOCOL=${STUB_PROTOCOL} but no certificate is present at $CERT_DIR." >&2
    echo "Expected an uploaded cert to be mounted there, or TLS_CERT_SOURCE=AUTO_GENERATED." >&2
    exit 1
  fi

  chmod 600 "$CERT_DIR/server.key.pem"
  [ -f "$CERT_DIR/ca-bundle.pem" ] && chmod 644 "$CERT_DIR/ca-bundle.pem"

  nginx -g 'daemon off;' &
  NGINX_PID=$!
fi

java $JAVA_OPTS -jar /app/app.jar &
JAVA_PID=$!

# Waits for whichever of the (up to two) background jobs above exits first.
# `|| EXIT_CODE=$?` (rather than a bare `wait -n; EXIT_CODE=$?`) matters here
# because `set -e` would otherwise kill this script at `wait -n` itself the
# moment the waited-for process exits non-zero, before its exit code could
# ever be captured or logged.
EXIT_CODE=0
wait -n || EXIT_CODE=$?
echo "A stub-engine process exited (code $EXIT_CODE) — stopping the container so it restarts cleanly."
term_handler
