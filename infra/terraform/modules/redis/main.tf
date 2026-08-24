# ElastiCache Redis module — caching and pub/sub

variable "name_prefix" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "node_type" { type = string }
variable "ecs_security_group" { type = string }

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.name_prefix}-redis-subnet"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name   = "${var.name_prefix}-redis-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.ecs_security_group]
  }

  tags = { Name = "${var.name_prefix}-redis-sg" }
}

resource "aws_elasticache_cluster" "main" {
  cluster_id      = "${var.name_prefix}-redis"
  engine          = "redis"
  engine_version  = "7.1"
  node_type       = var.node_type
  num_cache_nodes = 1
  port            = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  snapshot_retention_limit = 3

  tags = { Name = "${var.name_prefix}-redis" }
}

output "endpoint" {
  value = aws_elasticache_cluster.main.cache_nodes[0].address
}
