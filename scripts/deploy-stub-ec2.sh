#!/usr/bin/env bash
# ==============================================================================
# deploy-stub-ec2.sh
# Mockingbird Stub Engine — install / redeploy on RHEL8 EC2 (AWS)
# ==============================================================================
# Fully unattended. Pulls Amazon Corretto 21 + the stub-engine app.jar from
# S3, installs both, sets JAVA_HOME system-wide, and runs the stub as a
# systemd service. No general internet egress required — only S3, via an
# IAM instance profile (preferred) or the AWS CLI's configured credentials.
#
# Usage (run as root on the target EC2 instance):
#   sudo ./deploy-stub-ec2.sh
#
# Safe to re-run: this is also the redeploy script. Upload a new app.jar to
# the same S3 key and re-run — Java is skipped if already installed at the
# right version, the jar is always re-pulled, and the service is restarted.
# ==============================================================================

set -euo pipefail

# ── EDIT THESE ────────────────────────────────────────────────────────────────
S3_BUCKET="lre-poc-bucket"
JDK_S3_KEY="amazon-corretto-21.0.10.7.1-linux-x64.tar.gz"   # full key/path in the bucket
JAR_S3_KEY="app.jar"                                        # full key/path in the bucket
AWS_REGION="eu-west-2"                                        # bucket's region
# ─────────────────────────────────────────────────────────────────────────────

# Tunables — sensible defaults for c6a.4xlarge (16 vCPU / 32 GiB RAM).
INSTALL_DIR="/opt/mockingbird-stub"
JDK_DIR="/opt/corretto-21"
SERVICE_USER="mockingbird"
SERVICE_NAME="mockingbird-stub"
JAVA_HEAP="-Xmx24g"          # ~8GB headroom left for OS + JVM overhead
STUB_PORT="8080"
ACTUATOR_PORT="8081"
MIN_FREE_MB=2048             # /opt must have at least this much free before we extract anything

LOG_DIR="/var/log/mockingbird"
LOG_FILE="${LOG_DIR}/deploy_$(date +%Y%m%d_%H%M%S).log"

# ── logging ──────────────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"

_ts() { date +'%Y-%m-%d %H:%M:%S'; }

log()     { echo -e "[$(_ts)] [INFO]    $*" | tee -a "${LOG_FILE}"; }
step()    { echo -e "\n[$(_ts)] [STEP]    $*" | tee -a "${LOG_FILE}"; }
success() { echo -e "[$(_ts)] [SUCCESS] $*" | tee -a "${LOG_FILE}"; }
warn()    { echo -e "[$(_ts)] [WARN]    $*" | tee -a "${LOG_FILE}" >&2; }
fail()    { echo -e "[$(_ts)] [ERROR]   $*" | tee -a "${LOG_FILE}" >&2; exit 1; }

banner() {
  local line="=============================================================================="
  echo -e "\n${line}\n$*\n${line}" | tee -a "${LOG_FILE}"
}

banner "MOCKINGBIRD STUB DEPLOY  |  $(hostname)  |  $(_ts)"
log "Log file: ${LOG_FILE}"

# ==============================================================================
# PHASE 1 — PRE-FLIGHT CHECKS
# ==============================================================================
step "PHASE 1 — Pre-flight checks"

# 1.1 — root
[[ ${EUID} -eq 0 ]] || fail "Run as root (sudo ./deploy-stub-ec2.sh)."
success "[1.1] Running as root."

# 1.2 — OS sanity check (warn, don't block — the script only needs tar/systemd/aws)
if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  log "[1.2] Detected OS: ${PRETTY_NAME:-unknown}"
  [[ "${ID:-}" == "rhel" ]] || warn "[1.2] Expected RHEL — found '${ID:-unknown}'. Continuing anyway."
else
  warn "[1.2] /etc/os-release not found — cannot confirm OS. Continuing anyway."
fi

# 1.3 — required commands
for cmd in tar systemctl curl; do
  command -v "${cmd}" >/dev/null 2>&1 || fail "[1.3] Required command '${cmd}' not found on this host."
done
success "[1.3] tar, systemctl, curl present."

# 1.4 — disk space under /opt
free_mb=$(df -Pm /opt | awk 'NR==2 {print $4}')
if [[ "${free_mb}" -lt ${MIN_FREE_MB} ]]; then
  fail "[1.4] Only ${free_mb}MB free under /opt — need at least ${MIN_FREE_MB}MB."
fi
success "[1.4] Disk space OK (${free_mb}MB free under /opt)."

# 1.5 — AWS CLI present (install best-effort; this host may have no general repo access)
if ! command -v aws >/dev/null 2>&1; then
  log "[1.5] aws CLI not found — attempting 'dnf install -y awscli' ..."
  if ! dnf install -y awscli >>"${LOG_FILE}" 2>&1; then
    fail "[1.5] aws CLI is not installed and could not be installed via dnf. If this box has no \
general internet/repo access, stage the AWS CLI v2 installer bundle in S3 the same way you did \
Corretto, install it manually, then re-run this script."
  fi
fi
log "[1.5] $(aws --version 2>&1)"
success "[1.5] AWS CLI available."

# 1.6 — confirm both S3 objects actually exist before downloading anything
log "[1.6] Checking S3 objects are reachable ..."
aws s3api head-object --bucket "${S3_BUCKET}" --key "${JDK_S3_KEY}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || fail "[1.6] s3://${S3_BUCKET}/${JDK_S3_KEY} not found or not accessible. Check the key path, \
bucket, region, and that this instance's IAM role has s3:GetObject on it."
aws s3api head-object --bucket "${S3_BUCKET}" --key "${JAR_S3_KEY}" --region "${AWS_REGION}" >/dev/null 2>&1 \
  || fail "[1.6] s3://${S3_BUCKET}/${JAR_S3_KEY} not found or not accessible."
success "[1.6] Both S3 objects confirmed reachable."

# ==============================================================================
# PHASE 2 — JAVA (Amazon Corretto 21)
# ==============================================================================
step "PHASE 2 — Java runtime"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

# 2.1 — skip re-install if the right version is already there (idempotent)
already_have_java=false
if [[ -x "${JDK_DIR}/bin/java" ]]; then
  installed_ver="$("${JDK_DIR}/bin/java" -version 2>&1 | head -1)"
  if [[ "${installed_ver}" == *'"21.'* ]]; then
    log "[2.1] Corretto 21 already installed at ${JDK_DIR} (${installed_ver}) — skipping download/extract."
    already_have_java=true
  else
    warn "[2.1] ${JDK_DIR} exists but reports '${installed_ver}' (not 21.x) — reinstalling."
  fi
fi

if [[ "${already_have_java}" == false ]]; then
  log "[2.2] Downloading Corretto JDK from s3://${S3_BUCKET}/${JDK_S3_KEY}"
  aws s3 cp "s3://${S3_BUCKET}/${JDK_S3_KEY}" "${WORKDIR}/corretto.tar.gz" --region "${AWS_REGION}" \
    | tee -a "${LOG_FILE}"

  log "[2.3] Installing Corretto 21 to ${JDK_DIR}"
  # Clear out any stale/wrong-version install first (the ${JDK_DIR:?} guard
  # makes this fail loudly instead of rm -rf'ing "/" if the variable were
  # ever accidentally empty).
  rm -rf "${JDK_DIR:?}"
  mkdir -p "${JDK_DIR}"
  # --strip-components=1 handles whatever the tarball's top-level folder is
  # named (e.g. amazon-corretto-21.0.10.7.1-linux-x64/) without hardcoding it.
  tar -xzf "${WORKDIR}/corretto.tar.gz" -C "${JDK_DIR}" --strip-components=1
fi

[[ -x "${JDK_DIR}/bin/java" ]] || fail "[2.4] ${JDK_DIR}/bin/java not found after install."
java_version_output="$("${JDK_DIR}/bin/java" -version 2>&1 | head -1)"
[[ "${java_version_output}" == *'"21.'* ]] || fail "[2.4] Installed Java reports unexpected version: ${java_version_output}"
success "[2.4] Java verified: ${java_version_output}"

# 2.5 — JAVA_HOME + PATH, system-wide (for anyone who logs in and needs
# jcmd/jstat/jmap for troubleshooting, not just the systemd service below).
log "[2.5] Setting JAVA_HOME system-wide via /etc/profile.d/corretto21.sh"
cat > /etc/profile.d/corretto21.sh <<EOF
export JAVA_HOME=${JDK_DIR}
export PATH=\${JAVA_HOME}/bin:\${PATH}
EOF
chmod 644 /etc/profile.d/corretto21.sh
success "[2.5] JAVA_HOME=${JDK_DIR} exported for all users (new shells)."

# ==============================================================================
# PHASE 3 — STUB-ENGINE JAR
# ==============================================================================
step "PHASE 3 — Stub-engine jar"

log "[3.1] Downloading jar from s3://${S3_BUCKET}/${JAR_S3_KEY}"
mkdir -p "${INSTALL_DIR}"
aws s3 cp "s3://${S3_BUCKET}/${JAR_S3_KEY}" "${WORKDIR}/app.jar" --region "${AWS_REGION}" \
  | tee -a "${LOG_FILE}"

[[ -s "${WORKDIR}/app.jar" ]] || fail "[3.1] Downloaded app.jar is empty or missing."

if [[ -f "${INSTALL_DIR}/app.jar" ]]; then
  cp "${INSTALL_DIR}/app.jar" "${INSTALL_DIR}/app.jar.bak_$(date +%Y%m%d_%H%M%S)"
  log "[3.2] Existing app.jar backed up."
fi
cp "${WORKDIR}/app.jar" "${INSTALL_DIR}/app.jar"
success "[3.2] app.jar installed to ${INSTALL_DIR}."

# ==============================================================================
# PHASE 4 — SERVICE USER & PERMISSIONS
# ==============================================================================
step "PHASE 4 — Service user"

if id "${SERVICE_USER}" >/dev/null 2>&1; then
  log "[4.1] Service user '${SERVICE_USER}' already exists."
else
  useradd -r -s /sbin/nologin "${SERVICE_USER}"
  success "[4.1] Created service user '${SERVICE_USER}'."
fi
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
success "[4.2] Ownership set on ${INSTALL_DIR}."

# ==============================================================================
# PHASE 5 — SYSTEMD SERVICE
# ==============================================================================
step "PHASE 5 — systemd service"

log "[5.1] Writing /etc/systemd/system/${SERVICE_NAME}.service"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Mockingbird Stub Engine
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment="JAVA_HOME=${JDK_DIR}"
Environment="JAVA_OPTS=${JAVA_HEAP} -XX:+UseG1GC -XX:MaxGCPauseMillis=10 -XX:+UseStringDeduplication"
ExecStart=/bin/sh -c '\${JAVA_HOME}/bin/java \${JAVA_OPTS} -jar ${INSTALL_DIR}/app.jar --server.port=${STUB_PORT} --management.server.port=${ACTUATOR_PORT}'
Restart=on-failure
RestartSec=5
User=${SERVICE_USER}

[Install]
WantedBy=multi-user.target
EOF
success "[5.1] Unit file written."

log "[5.2] Reloading systemd and (re)starting ${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >>"${LOG_FILE}" 2>&1
systemctl restart "${SERVICE_NAME}"
success "[5.2] Service enabled and (re)started."

# ==============================================================================
# PHASE 6 — VERIFY
# ==============================================================================
step "PHASE 6 — Verification"

log "[6.1] Waiting for health check on port ${ACTUATOR_PORT} ..."
healthy=false
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${ACTUATOR_PORT}/actuator/health" >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 1
done

if [[ "${healthy}" == true ]]; then
  success "[6.1] Health check passed."
  curl -s "http://localhost:${ACTUATOR_PORT}/actuator/health" | tee -a "${LOG_FILE}"; echo
else
  warn "[6.1] Health check did not pass within 30s. Recent service log:"
  journalctl -u "${SERVICE_NAME}" -n 40 --no-pager | tee -a "${LOG_FILE}"
  fail "[6.1] Deployment did not come up healthy — see log above and: journalctl -u ${SERVICE_NAME} -f"
fi

log "[6.2] Checking systemd unit is active ..."
systemctl is-active --quiet "${SERVICE_NAME}" && success "[6.2] ${SERVICE_NAME} is active." \
  || fail "[6.2] ${SERVICE_NAME} is not active despite a passing health check — investigate."

# ==============================================================================
# SUMMARY
# ==============================================================================
private_ip="$(hostname -I | awk '{print $1}')"
banner "MOCKINGBIRD STUB DEPLOY COMPLETE  |  $(hostname)"
log "Stub traffic:    http://${private_ip}:${STUB_PORT}"
log "Actuator health: http://${private_ip}:${ACTUATOR_PORT}/actuator/health"
log "Service:         systemctl status ${SERVICE_NAME}"
log "Logs (service):  journalctl -u ${SERVICE_NAME} -f"
log "Logs (deploy):   ${LOG_FILE}"
log ""
warn "REMAINING MANUAL STEP: confirm the EC2 Security Group allows inbound ${STUB_PORT} \
(and ${ACTUATOR_PORT} if you need remote health checks) from your NFT testers'/JMeter host's CIDR only."
log "Point JMeter at this box with: jmeter -n -t test-plan.jmx -l results.jtl -JHOST=${private_ip} -JPORT=${STUB_PORT}"
