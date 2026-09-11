#!/usr/bin/env bash
# Set up the Mockingbird stub on a RHEL9/RHEL10 EC2 box as a standalone JAR
# (no Docker) — an alternative to the Terraform/Docker auto-deploy path in
# terraform/stub-ec2/ for teams running a manual EC2 POC.
#
# Downloads Java + the app jar from S3, installs Java, and runs the stub as
# a systemd service (under a dedicated non-root user) that restarts on
# failure and starts on boot.
#
# Run as root:   sudo ./deploy-stub-ec2.sh
#
# Requirements:
#   - The instance must have an IAM role/instance profile with S3 read access
#     to the bucket below (the script verifies this before doing any work).
#   - Internet/repo access to install the AWS CLI if it is not already present.
#
# NOTE: this path does not (yet) support the HTTPS/mTLS stub protocol —
# that's only wired into the Docker image built by the Terraform auto-deploy
# path (see terraform/stub-ec2/ and docs/STUB_HTTPS_MTLS_DESIGN.md), because
# TLS termination there runs via nginx baked into that image. A stub
# deployed with this script always serves plain HTTP on 8080.

set -euo pipefail

# ---- change these to match your S3 files — the script refuses to run
# ---- until every CHANGE_ME is replaced with a real value ----
BUCKET="CHANGE_ME_your-s3-bucket"
JAVA_FILE="CHANGE_ME_corretto-21-linux-x64.tar.gz"
JAR_FILE="CHANGE_ME_your-stub-app.jar"
REGION="CHANGE_ME_aws-region"

# ---- where things get installed ----
JAVA_DIR="/opt/corretto-21"
APP_DIR="/opt/mockingbird-stub"
SERVICE_USER="mockingbird"
HEALTH_URL="http://localhost:8081/actuator/health"

# ---- heap size: default to ~50% of RAM, capped at 24g, min 1g ----
# Override by exporting MOCK_XMX before running, e.g. MOCK_XMX=8g sudo -E ./script
XMX="${MOCK_XMX:-}"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# --- must run as root (systemd + /opt + /etc writes) ---
if [ "$(id -u)" -ne 0 ]; then
    fail "This script must be run as root (use: sudo $0)"
fi

# --- refuse to run against unedited placeholder config ---
for var in BUCKET JAVA_FILE JAR_FILE REGION; do
    case "${!var}" in
        CHANGE_ME*)
            fail "$var is still set to its placeholder value (${!var}). Edit the top of this script with your real S3 bucket/keys/region before running."
            ;;
    esac
done

# --- OS package patching (CVE remediation) ---------------------------------
# Runs a full `dnf update -y` before anything else so the box is patched
# before the stub goes live. Set SKIP_OS_UPDATE=1 to skip (e.g. in PROD where
# patching is controlled separately / requires a change window, or on a
# REDEPLOY where the box was already patched on first install — see the
# "Redeploy a new jar" section of the runbook).
# NOTE: kernel/glibc updates only take effect after a reboot — schedule one
# if the update pulls a new kernel.
os_update() {
    if [ "${SKIP_OS_UPDATE:-0}" = "1" ]; then
        log "SKIP_OS_UPDATE=1 set — skipping 'dnf update'."
        return
    fi
    if command -v dnf >/dev/null 2>&1; then
        log "Patching OS packages (dnf update -y) — this may take a few minutes..."
        dnf update -y || fail "dnf update failed"
        log "OS packages patched. A reboot may be required if the kernel was updated."
    else
        log "dnf not found — skipping OS update (non-RHEL host?)."
    fi
}

# --- dedicated service user: the stub must not run as root -----------------
ensure_service_user() {
    if id "$SERVICE_USER" >/dev/null 2>&1; then
        log "Service user '$SERVICE_USER' already exists."
    else
        log "Creating dedicated service user '$SERVICE_USER' (no login, no home dir)..."
        useradd --system --no-create-home --shell /sbin/nologin "$SERVICE_USER" \
            || fail "Failed to create service user '$SERVICE_USER'"
    fi
}

# --- firewall: open the stub port so load generators can reach it ----------
# The stub serves client traffic on 8080; the whole point of the box is to be
# reachable there. 8081 (actuator/Prometheus) is deliberately NOT opened to the
# world — scrape it over the internal monitoring path only. Set
# OPEN_ACTUATOR_CIDR=10.x.x.x/xx to allow 8081 from a specific monitoring range.
configure_firewall() {
    if ! command -v firewall-cmd >/dev/null 2>&1; then
        log "firewalld not present — skipping firewall config (ensure 8080 is reachable by other means)."
        return
    fi
    if ! systemctl is-active --quiet firewalld; then
        log "firewalld installed but not active — skipping (nothing blocking 8080 locally)."
        return
    fi
    log "Opening stub port 8080/tcp in firewalld..."
    firewall-cmd --permanent --add-port=8080/tcp >/dev/null 2>&1 || fail "Failed to open 8080/tcp"
    if [ -n "${OPEN_ACTUATOR_CIDR:-}" ]; then
        log "Allowing actuator 8081/tcp from ${OPEN_ACTUATOR_CIDR}..."
        firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${OPEN_ACTUATOR_CIDR} port port=8081 protocol=tcp accept" >/dev/null 2>&1 || true
    fi
    firewall-cmd --reload >/dev/null 2>&1 || fail "firewall-cmd --reload failed"
    log "Firewall open ports: $(firewall-cmd --list-ports 2>/dev/null)"
}

# --- OS tuning for high TPS (sockets, ephemeral ports, accept backlog) ----
# At several-thousand-plus TPS the host accepts and recycles a very large
# number of short-lived sockets. Defaults (1024 FDs, ~28k ephemeral ports,
# somaxconn 128/4096) throttle throughput and cause accept-queue drops. These
# match WireMock's jettyAcceptQueueSize(1000) and the 10K-TPS target.
tune_os_for_tps() {
    log "Applying kernel tuning for high TPS..."
    cat > /etc/sysctl.d/99-mockingbird-stub.conf <<'EOF'
# Widen ephemeral port range (more concurrent outbound/return sockets)
net.ipv4.ip_local_port_range = 1024 65535
# Recycle TIME_WAIT sockets faster for new connections
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
# Accept queue / backlog — must be >= Jetty's acceptQueueSize(1000)
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 8192
net.core.netdev_max_backlog = 16384
EOF
    sysctl --system >/dev/null 2>&1 || log "WARNING: sysctl --system reported an issue; continuing."
    log "Kernel tuning applied (/etc/sysctl.d/99-mockingbird-stub.conf)."
}

# --- resolve the AWS CLI; install it on RHEL9/10 if missing ---
resolve_or_install_aws_cli() {
    AWS_CLI="$(command -v aws 2>/dev/null || true)"
    if [ -z "$AWS_CLI" ] && [ -x /usr/local/bin/aws ]; then
        AWS_CLI="/usr/local/bin/aws"
    fi
    if [ -n "$AWS_CLI" ]; then
        log "Found AWS CLI: $AWS_CLI ($("$AWS_CLI" --version 2>&1))"
        return
    fi

    log "AWS CLI not found - installing it..."
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y unzip >/dev/null 2>&1 || fail "Failed to install 'unzip' (needed to unpack the AWS CLI)"
    elif command -v yum >/dev/null 2>&1; then
        yum install -y unzip >/dev/null 2>&1 || fail "Failed to install 'unzip'"
    fi

    local tmp
    tmp="$(mktemp -d)"
    if ! curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$tmp/awscliv2.zip"; then
        rm -rf "$tmp"
        fail "Could not download the AWS CLI installer (check network/proxy access)"
    fi
    ( cd "$tmp" && unzip -q awscliv2.zip && ./aws/install >/dev/null 2>&1 ) \
        || { rm -rf "$tmp"; fail "AWS CLI installation failed"; }
    rm -rf "$tmp"

    AWS_CLI="$(command -v aws 2>/dev/null || echo /usr/local/bin/aws)"
    [ -x "$AWS_CLI" ] || fail "AWS CLI still not available after install"
    log "AWS CLI installed: $("$AWS_CLI" --version 2>&1)"
}

# --- preflight: credentials + both S3 objects must be reachable ---
preflight_checks() {
    log "Verifying AWS credentials (instance role)..."
    "$AWS_CLI" sts get-caller-identity --region "$REGION" >/dev/null 2>&1 \
        || fail "No usable AWS credentials. Attach an IAM instance profile with S3 read access, then retry."

    log "Verifying S3 objects exist..."
    "$AWS_CLI" s3api head-object --bucket "$BUCKET" --key "$JAVA_FILE" --region "$REGION" >/dev/null 2>&1 \
        || fail "Java file not found: s3://$BUCKET/$JAVA_FILE"
    "$AWS_CLI" s3api head-object --bucket "$BUCKET" --key "$JAR_FILE" --region "$REGION" >/dev/null 2>&1 \
        || fail "App jar not found: s3://$BUCKET/$JAR_FILE"
    log "S3 objects present."
}

# --- pick a sane heap size if the caller didn't set one ---
compute_xmx() {
    if [ -n "$XMX" ]; then
        log "Using caller-provided heap: -Xmx$XMX"
        return
    fi
    local mem_kb mem_mb half_mb
    mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
    mem_mb=$(( mem_kb / 1024 ))
    half_mb=$(( mem_mb / 2 ))
    if   [ "$half_mb" -ge 24576 ]; then XMX="24g"
    elif [ "$half_mb" -ge 1024 ];  then XMX="$(( half_mb / 1024 ))g"
    else XMX="1g"
    fi
    log "Auto-selected heap: -Xmx$XMX (system RAM ~${mem_mb} MB, ~50% of it)"
}

main() {
    os_update
    ensure_service_user
    resolve_or_install_aws_cli
    preflight_checks
    compute_xmx
    tune_os_for_tps

    log "Step 1: Preparing directories..."
    mkdir -p "$APP_DIR" "$JAVA_DIR"

    log "Step 2: Downloading Java from S3..."
    "$AWS_CLI" s3 cp "s3://$BUCKET/$JAVA_FILE" /tmp/java.tar.gz --region "$REGION" --no-progress \
        || fail "Failed to download $JAVA_FILE"

    log "Step 3: Installing Java to $JAVA_DIR..."
    tar -xzf /tmp/java.tar.gz -C "$JAVA_DIR" --strip-components=1 \
        || fail "Failed to extract Java"
    "$JAVA_DIR/bin/java" -version || fail "Java did not run after extraction"
    rm -f /tmp/java.tar.gz

    log "Step 4: Exporting JAVA_HOME system-wide (/etc/profile.d/java.sh)..."
    cat > /etc/profile.d/java.sh <<EOF
export JAVA_HOME=$JAVA_DIR
export PATH=\$JAVA_HOME/bin:\$PATH
EOF
    chmod 644 /etc/profile.d/java.sh

    log "Step 5: Downloading the stub jar from S3..."
    "$AWS_CLI" s3 cp "s3://$BUCKET/$JAR_FILE" "$APP_DIR/app.jar" --region "$REGION" --no-progress \
        || fail "Failed to download $JAR_FILE"
    [ -s "$APP_DIR/app.jar" ] || fail "Downloaded app.jar is missing or empty"

    log "Step 6: Setting ownership of $APP_DIR to '$SERVICE_USER' (the stub does not run as root)..."
    chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

    log "Step 7: Creating the systemd service..."
    cat > /etc/systemd/system/mockingbird-stub.service <<EOF
[Unit]
Description=Mockingbird Stub Engine
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$JAVA_DIR/bin/java -Xmx$XMX -XX:+UseG1GC -XX:MaxGCPauseMillis=10 -XX:+UseStringDeduplication -jar $APP_DIR/app.jar
Restart=on-failure
RestartSec=5
# High TPS needs far more than the default 1024 open file descriptors —
# every concurrent socket is an FD. 1M is comfortable headroom for 10K TPS.
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

    log "Step 8: Configuring the firewall (open stub port 8080)..."
    configure_firewall

    log "Step 9: Starting the stub service..."
    systemctl daemon-reload
    systemctl enable mockingbird-stub >/dev/null 2>&1 || true
    systemctl restart mockingbird-stub

    # Give it a moment, then report status honestly.
    sleep 5
    if systemctl is-active --quiet mockingbird-stub; then
        log "Service mockingbird-stub is running (as user '$SERVICE_USER')."
    else
        log "WARNING: service is not active yet. Recent logs:"
        journalctl -u mockingbird-stub -n 30 --no-pager || true
        fail "mockingbird-stub failed to start (see logs above)"
    fi

    echo ""
    log "Done."
    echo "  Health:   curl $HEALTH_URL"
    echo "  Logs:     journalctl -u mockingbird-stub -f"
    echo "  Stop:     systemctl stop mockingbird-stub"
    echo "  Redeploy: upload a new $JAR_FILE to S3, then re-run this script."
    echo "            For a fast redeploy (skip OS re-patching): SKIP_OS_UPDATE=1 sudo -E $0"
}

main "$@"
