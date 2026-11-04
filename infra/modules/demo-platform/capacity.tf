variable "min_tasks" {
  type    = number
  default = 1
  validation {
    condition     = var.min_tasks >= 1 && var.min_tasks <= 5 && floor(var.min_tasks) == var.min_tasks
    error_message = "Use an integer API minimum from 1 to 5."
  }
}
variable "worker_max_tasks" {
  type    = number
  default = 1
  validation {
    condition     = var.worker_max_tasks >= 1 && var.worker_max_tasks <= 5 && floor(var.worker_max_tasks) == var.worker_max_tasks
    error_message = "Use an integer worker maximum from 1 to 5."
  }
}
variable "worker_min_tasks" {
  type    = number
  default = 1
  validation {
    condition     = var.worker_min_tasks >= 1 && var.worker_min_tasks <= 5 && floor(var.worker_min_tasks) == var.worker_min_tasks
    error_message = "Use an integer worker minimum from 1 to 5."
  }
}
variable "lambda_concurrency" {
  type    = number
  default = 1
  validation {
    condition     = var.lambda_concurrency >= 1 && var.lambda_concurrency <= 20 && floor(var.lambda_concurrency) == var.lambda_concurrency
    error_message = "Use Lambda concurrency from 1 to 20. FIFO group ordering still applies."
  }
}
variable "database_multi_az" {
  description = "Enable an RDS synchronous standby and managed AZ failover. False keeps one DB for the demo."
  type        = bool
  default     = false
}
variable "redis_node_count" {
  description = "One primary plus optional replicas. Two or more enables Redis Multi-AZ/automatic failover."
  type        = number
  default     = 1
  validation {
    condition     = var.redis_node_count >= 1 && var.redis_node_count <= 5 && floor(var.redis_node_count) == var.redis_node_count
    error_message = "Use one to five cache nodes."
  }
}
variable "nat_gateway_count" {
  description = "One demo gateway or two gateways with AZ-local routes."
  type        = number
  default     = 1
  validation {
    condition     = contains([1, 2], var.nat_gateway_count)
    error_message = "Use one or two NAT gateways."
  }
}
variable "turn_capacity" {
  description = "Managed TURN ASG and stable address-pool bounds. Demo: all one. Increase min/desired for hot relay redundancy and max for CPU scale-out."
  type        = object({ min = number, desired = number, max = number })
  default     = { min = 1, desired = 1, max = 1 }
  validation {
    condition     = var.turn_capacity.min >= 1 && var.turn_capacity.min <= var.turn_capacity.desired && var.turn_capacity.desired <= var.turn_capacity.max && var.turn_capacity.max <= 5 && alltrue([for value in values(var.turn_capacity) : floor(value) == value])
    error_message = "TURN requires integer 1 <= min <= desired <= max <= 5."
  }
}

locals {
  workload_subnets = local.managed ? aws_subnet.private[*].id : [aws_subnet.private[0].id]
  turn_addresses   = local.managed ? aws_eip.turn[*].public_ip : aws_eip.utility[*].public_ip
  turn_urls        = var.enable_turn ? flatten([for ip in local.turn_addresses : ["turn:${ip}:3478?transport=udp", "turn:${ip}:3478?transport=tcp"]]) : []
  # Hard singleton exceptions reflect current application/provider constraints.
  # Consultation HTTP is stateless in the managed layout; PeerJS itself stays one.
  api_maximum = { for service in local.services : service => (contains(local.managed ? [] : ["fulfilment", "consultation"], service) ? 1 : var.max_tasks) }
  api_minimum = { for service in local.services : service => min(var.min_tasks, local.api_maximum[service]) }
}
