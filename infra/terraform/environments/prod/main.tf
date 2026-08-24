# WMS QuickStart — Production Environment
# AWS infrastructure: VPC + ECS Fargate + RDS PostgreSQL + ElastiCache Redis + ALB + S3

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 (create bucket manually first)
  backend "s3" {
    bucket = "wms-quickstart-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "wms-quickstart"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ─── Variables ───

variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  default = "prod"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "app_image" {
  description = "ECR image URI for the backend"
  type        = string
}

locals {
  name_prefix = "wms-${var.environment}"
}

# ─── VPC ───

module "vpc" {
  source = "../modules/vpc"

  name_prefix = local.name_prefix
  cidr_block  = "10.0.0.0/16"
  az_count    = 2
}

# ─── RDS PostgreSQL ───

module "rds" {
  source = "../modules/rds"

  name_prefix        = local.name_prefix
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  db_name            = "wms"
  db_username        = "wms"
  db_password        = var.db_password
  instance_class     = "db.t4g.medium"  # Scale to db.r6g.large at 10+ tenants
  multi_az           = true
  ecs_security_group = module.ecs.ecs_security_group_id
}

# ─── ElastiCache Redis ───

module "redis" {
  source = "../modules/redis"

  name_prefix        = local.name_prefix
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  node_type          = "cache.t4g.micro"  # Scale to cache.t4g.small at 10+ tenants
  ecs_security_group = module.ecs.ecs_security_group_id
}

# ─── S3 ───

module "s3" {
  source = "../modules/s3"

  name_prefix = local.name_prefix
  environment = var.environment
}

# ─── ECS Fargate ───

module "ecs" {
  source = "../modules/ecs"

  name_prefix        = local.name_prefix
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  app_image          = var.app_image
  app_port           = 8000

  database_url = "postgresql+asyncpg://${module.rds.db_username}:${var.db_password}@${module.rds.db_endpoint}/${module.rds.db_name}"
  redis_url    = "redis://${module.redis.endpoint}:6379/0"
  jwt_secret   = var.jwt_secret
  s3_bucket    = module.s3.bucket_name

  # Scaling
  api_desired_count    = 2
  api_cpu              = 512   # 0.5 vCPU
  api_memory           = 1024  # 1 GB
  worker_desired_count = 1
  worker_cpu           = 512
  worker_memory        = 1024
}

# ─── Outputs ───

output "alb_dns" {
  value = module.ecs.alb_dns_name
}

output "rds_endpoint" {
  value = module.rds.db_endpoint
}

output "s3_bucket" {
  value = module.s3.bucket_name
}
