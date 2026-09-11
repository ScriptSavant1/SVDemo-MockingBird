terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend is configured dynamically via -backend-config flags in the deployer-worker.
  # State key: stubs/{project_id}/{stub_id}/terraform.tfstate
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

# ── Data: latest Amazon Linux 2023 AMI ───────────────────────────────────────

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# ── Elastic IP (allocated before EC2 so stub_url is known before launch) ─────

resource "aws_eip" "stub" {
  domain = "vpc"

  tags = {
    Name       = "mockingbird-stub-${var.project_id}-${var.stub_id}"
    Project    = var.project_id
    Stub       = var.stub_id
    ManagedBy  = "mockingbird-terraform"
  }
}

# ── EIP Association (links EIP to the instance after launch) ─────────────────

resource "aws_eip_association" "stub" {
  instance_id   = aws_instance.stub.id
  allocation_id = aws_eip.stub.id
}

# ── EC2 instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "stub" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  key_name               = var.key_name
  iam_instance_profile   = var.iam_instance_profile

  # JVM flags for 12K–18K TPS (c6i.2xlarge: 8 vCPU, 16 GB)
  #
  # HTTPS/mTLS (see docs/STUB_HTTPS_MTLS_DESIGN.md): when stub_protocol !=
  # HTTP, nginx runs inside the same container (entrypoint.sh) terminating
  # TLS on :443 in front of WireMock's unchanged :8080. For an HTTPS-only
  # project, 8080 is deliberately NOT published on the host at all — nginx
  # on 443 is the only way in, so a client can't bypass TLS by hitting 8080
  # directly. 8081 (actuator/metrics) is always published regardless of
  # protocol; it's never routed through nginx.
  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -euxo pipefail

    # Install Docker
    dnf install -y docker
    systemctl enable --now docker

    # Log in to GitLab Container Registry
    echo "${var.gitlab_registry_token}" | \
      docker login "${split("/", var.docker_image)[0]}" \
        -u deploy-token --password-stdin

    # Pull the stub engine
    docker pull "${var.docker_image}"

    PORT_ARGS="-p 8081:8081"
    CERT_MOUNT_ARGS=""

    %{ if var.stub_protocol == "HTTP" }
    PORT_ARGS="$PORT_ARGS -p 8080:8080"
    %{ endif }
    %{ if var.stub_protocol == "BOTH" }
    PORT_ARGS="$PORT_ARGS -p 8080:8080 -p 443:443"
    %{ endif }
    %{ if var.stub_protocol == "HTTPS" }
    PORT_ARGS="$PORT_ARGS -p 443:443"
    %{ endif }

    %{ if var.stub_protocol != "HTTP" }
    dnf install -y awscli
    mkdir -p /opt/mockingbird-stub/certs
    %{ if var.tls_cert_s3_uri != "" }
    aws s3 cp "${var.tls_cert_s3_uri}" /opt/mockingbird-stub/certs/server.crt.pem --region "${var.aws_region}"
    aws s3 cp "${var.tls_key_s3_uri}" /opt/mockingbird-stub/certs/server.key.pem --region "${var.aws_region}"
    %{ endif }
    %{ if var.tls_ca_bundle_s3_uri != "" }
    aws s3 cp "${var.tls_ca_bundle_s3_uri}" /opt/mockingbird-stub/certs/ca-bundle.pem --region "${var.aws_region}"
    %{ endif }
    CERT_MOUNT_ARGS="-v /opt/mockingbird-stub/certs:/etc/nginx/certs"
    %{ endif }

    docker run -d \
      --name stub-engine \
      --restart unless-stopped \
      $PORT_ARGS \
      $CERT_MOUNT_ARGS \
      -e STUB_API_KEY="${var.stub_api_key}" \
      -e STUB_PROTOCOL="${var.stub_protocol}" \
      -e MTLS_ENABLED="${var.mtls_enabled}" \
      -e TLS_CERT_SOURCE="${var.tls_cert_source}" \
      -e SPRING_JVM_OPTS="-Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10" \
      "${var.docker_image}"
  EOF
  )

  tags = {
    Name       = "mockingbird-stub-${var.project_id}-${var.stub_id}"
    Project    = var.project_id
    Stub       = var.stub_id
    ManagedBy  = "mockingbird-terraform"
  }

  lifecycle {
    # Replacing the instance destroys the EIP association first;
    # create_before_destroy ensures no downtime window for the EIP.
    create_before_destroy = true
  }
}
