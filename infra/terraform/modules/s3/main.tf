# S3 module — document storage (invoices, labels, imports)

variable "name_prefix" { type = string }
variable "environment" { type = string }

resource "aws_s3_bucket" "main" {
  bucket = "${var.name_prefix}-documents"
  tags   = { Name = "${var.name_prefix}-documents" }
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket                  = aws_s3_bucket.main.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: move old files to cheaper storage
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    id     = "archive-old-documents"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

output "bucket_name" { value = aws_s3_bucket.main.id }
output "bucket_arn" { value = aws_s3_bucket.main.arn }
