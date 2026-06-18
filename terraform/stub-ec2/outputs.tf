output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.stub.id
}

output "elastic_ip" {
  description = "Elastic IP address assigned to the stub engine"
  value       = aws_eip.stub.public_ip
}

output "stub_url" {
  description = "Stub engine base URL (HTTP, port 8080)"
  value       = "http://${aws_eip.stub.public_ip}:8080"
}
