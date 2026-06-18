variable "aws_region" {
  description = "AWS region to deploy the stub EC2 into"
  type        = string
  default     = "eu-west-2"
}

variable "project_id" {
  description = "Mockingbird project UUID (used for tagging and naming)"
  type        = string
}

variable "stub_id" {
  description = "Mockingbird stub UUID (used for tagging and image selection)"
  type        = string
}

variable "docker_image" {
  description = "Fully-qualified Docker image to run on this EC2 (from GitLab Container Registry)"
  type        = string
}

variable "stub_api_key" {
  description = "API key injected as STUB_API_KEY env var into the Spring Boot container"
  type        = string
  sensitive   = true
}

variable "subnet_id" {
  description = "VPC subnet ID to launch the EC2 instance into"
  type        = string
}

variable "security_group_id" {
  description = "Security group to attach (must allow inbound TCP 8080)"
  type        = string
}

variable "key_name" {
  description = "EC2 key pair name for SSH access (break-glass)"
  type        = string
  default     = "mockingbird-key"
}

variable "iam_instance_profile" {
  description = "IAM instance profile that allows the EC2 to pull from the GitLab Container Registry via Secrets Manager"
  type        = string
  default     = "MockingbirdStubInstanceProfile"
}

variable "ec2_instance_type" {
  description = "EC2 instance type: c6i.xlarge (<5K TPS) or c6i.2xlarge (≥5K TPS)"
  type        = string
  default     = "c6i.2xlarge"

  validation {
    condition     = contains(["c6i.xlarge", "c6i.2xlarge"], var.ec2_instance_type)
    error_message = "ec2_instance_type must be c6i.xlarge or c6i.2xlarge."
  }
}

variable "gitlab_registry_token" {
  description = "GitLab deploy token for docker pull (injected into user_data; retrieved from Vault/Secrets Manager by deployer-worker)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "java_base_image" {
  description = "Base Java 21 image URL from GitLab Container Registry (used by the stub-engine image)"
  type        = string
  default     = ""
}
