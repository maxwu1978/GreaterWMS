# RDS PostgreSQL module — multi-tenant database with encryption

variable "name_prefix" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_name" { type = string }
variable "db_username" { type = string }
variable "db_password" { type = string }
variable "instance_class" { type = string }
variable "multi_az" { type = bool }
variable "ecs_security_group" { type = string }

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db-subnet"
  subnet_ids = var.private_subnet_ids
  tags       = { Name = "${var.name_prefix}-db-subnet" }
}

resource "aws_security_group" "rds" {
  name   = "${var.name_prefix}-rds-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.ecs_security_group]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name_prefix}-rds-sg" }
}

resource "aws_db_instance" "main" {
  identifier = "${var.name_prefix}-db"

  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.instance_class

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az            = var.multi_az
  storage_type        = "gp3"
  allocated_storage   = 20
  max_allocated_storage = 100  # Auto-scaling storage

  storage_encrypted = true  # AES-256 at rest

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-db-final"

  performance_insights_enabled = true

  tags = { Name = "${var.name_prefix}-db" }
}

output "db_endpoint" { value = aws_db_instance.main.endpoint }
output "db_name" { value = aws_db_instance.main.db_name }
output "db_username" { value = aws_db_instance.main.username }
