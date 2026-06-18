# deployer-worker — Python 3.11 + Terraform CLI
# Build: cd services && docker build -f deployer-worker/Dockerfile -t deployer-worker .
# ARG PIP_INDEX_URL is set by GitLab CI from ARTIFACTORY_PYPI_URL

ARG PIP_INDEX_URL=https://pypi.org/simple
FROM python:3.11-slim

WORKDIR /app

# Install Terraform CLI (pinned for reproducibility)
ARG TERRAFORM_VERSION=1.8.5
RUN apt-get update && apt-get install -y curl unzip && \
    curl -fsSL https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip \
      -o /tmp/terraform.zip && \
    unzip /tmp/terraform.zip -d /usr/local/bin && \
    rm /tmp/terraform.zip && \
    terraform version && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy Terraform module (baked into the image — no network access needed at deploy time)
COPY terraform/stub-ec2 /app/terraform/stub-ec2

# Install Python dependencies
ARG PIP_INDEX_URL
COPY services/deployer-worker/pyproject.toml .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -e "."

COPY services/deployer-worker/src /app/src

ENV PYTHONPATH=/app/src

CMD ["sv-deploy-worker"]
