# Demo defaults only. Mechanisms remain provisioned when these limits are one.
variable "min_tasks" {
  type    = number
  default = 1
}
variable "max_tasks" {
  type    = number
  default = 1
}
variable "worker_min_tasks" {
  type    = number
  default = 1
}
variable "worker_max_tasks" {
  type    = number
  default = 1
}
variable "allow_scale_out" {
  type    = bool
  default = false
}
variable "lambda_concurrency" {
  type    = number
  default = 1
}
variable "database_multi_az" {
  type    = bool
  default = false
}
variable "redis_node_count" {
  type    = number
  default = 1
}
variable "nat_gateway_count" {
  type    = number
  default = 1
}
variable "turn_capacity" {
  type    = object({ min = number, desired = number, max = number })
  default = { min = 1, desired = 1, max = 1 }
}
