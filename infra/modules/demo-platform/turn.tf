# Managed relay fleet. EIPs belong to the pool, not to disposable ASG instances.
resource "aws_eip" "turn" {
  count  = local.managed && var.enable_turn ? var.turn_capacity.max : 0
  domain = "vpc"
  tags   = { Project = var.name_prefix, Name = "${var.name_prefix}-turn-${count.index}" }
}
resource "aws_iam_role_policy" "turn_lifecycle" {
  count = local.managed && var.enable_turn ? 1 : 0
  role  = aws_iam_role.utility[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ec2:DescribeAddresses", "autoscaling:DescribeAutoScalingInstances"], Resource = "*" },
      { Effect = "Allow", Action = ["ec2:AssociateAddress"], Resource = [for address in aws_eip.turn : "arn:aws:ec2:ap-southeast-1:${data.aws_caller_identity.current.account_id}:elastic-ip/${address.id}"] },
      { Effect = "Allow", Action = ["ec2:AssociateAddress"], Resource = "arn:aws:ec2:ap-southeast-1:${data.aws_caller_identity.current.account_id}:instance/*", Condition = { StringEquals = { "ec2:ResourceTag/Project" = var.name_prefix } } },
      { Effect = "Allow", Action = ["ec2:AssociateAddress"], Resource = "arn:aws:ec2:ap-southeast-1:${data.aws_caller_identity.current.account_id}:network-interface/*", Condition = { ArnEquals = { "ec2:Vpc" = aws_vpc.demo.arn } } },
      { Effect = "Allow", Action = ["autoscaling:CompleteLifecycleAction", "autoscaling:SetInstanceHealth"], Resource = "arn:aws:autoscaling:ap-southeast-1:${data.aws_caller_identity.current.account_id}:autoScalingGroup:*:autoScalingGroupName/${var.name_prefix}-turn" }
    ]
  })
}
resource "aws_launch_template" "turn" {
  count                  = local.managed && var.enable_turn ? 1 : 0
  name_prefix            = "${var.name_prefix}-turn-"
  image_id               = data.aws_ssm_parameter.ubuntu[0].value
  instance_type          = "t4g.nano"
  update_default_version = true
  iam_instance_profile { arn = aws_iam_instance_profile.utility[0].arn }
  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [aws_security_group.utility.id]
    delete_on_termination       = true
  }
  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_type           = "gp3"
      volume_size           = 8
      encrypted             = true
      delete_on_termination = true
    }
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  monitoring { enabled = true }
  credit_specification { cpu_credits = "standard" }
  user_data = base64encode(templatefile("${path.module}/turn.sh.tftpl", {
    agent = file("${path.module}/turn_agent.py")
    config = jsonencode({
      region      = "ap-southeast-1", group = "${var.name_prefix}-turn", hook = "turn-ready",
      allocations = aws_eip.turn[*].id, secret_arn = aws_secretsmanager_secret.config["turn"].arn,
      realm       = var.origin_hostname
    })
  }))
  tag_specifications {
    resource_type = "instance"
    tags          = { Project = var.name_prefix, Name = "${var.name_prefix}-turn" }
  }
}
resource "aws_autoscaling_group" "turn" {
  count                     = local.managed && var.enable_turn ? 1 : 0
  name                      = "${var.name_prefix}-turn"
  min_size                  = var.enable_workloads ? var.turn_capacity.min : 0
  desired_capacity          = var.enable_workloads ? var.turn_capacity.desired : 0
  max_size                  = var.enable_workloads ? var.turn_capacity.max : 0
  vpc_zone_identifier       = aws_subnet.public[*].id
  health_check_type         = "EC2"
  health_check_grace_period = 300
  wait_for_capacity_timeout = "20m"
  enabled_metrics           = ["GroupDesiredCapacity", "GroupInServiceInstances", "GroupPendingInstances", "GroupTerminatingInstances"]
  launch_template {
    id      = aws_launch_template.turn[0].id
    version = tostring(aws_launch_template.turn[0].latest_version)
  }
  initial_lifecycle_hook {
    name                 = "turn-ready"
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
    heartbeat_timeout    = 900
    default_result       = "ABANDON"
  }
  instance_maintenance_policy {
    min_healthy_percentage = var.turn_capacity.min > 1 ? 50 : 0
    max_healthy_percentage = 100
  }
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = var.turn_capacity.min > 1 ? 50 : 0
      max_healthy_percentage = 100
      instance_warmup        = 180
    }
  }
  tag {
    key                 = "Project"
    value               = var.name_prefix
    propagate_at_launch = true
  }
  # ASG owns desired after creation. Min/max changes still enforce the bounds;
  # disabled workloads use max=0 so autoscaled desired cannot keep hosts alive.
  lifecycle { ignore_changes = [desired_capacity] }
  depends_on = [terraform_data.guards, aws_iam_role_policy.turn_lifecycle, aws_iam_role_policy.utility_secret, aws_route.internet]
}
resource "aws_autoscaling_policy" "turn_cpu" {
  count                  = local.managed && var.enable_turn && var.enable_workloads ? 1 : 0
  name                   = "${var.name_prefix}-turn-cpu"
  autoscaling_group_name = aws_autoscaling_group.turn[0].name
  policy_type            = "TargetTrackingScaling"
  target_tracking_configuration {
    target_value     = 60
    disable_scale_in = true # Live allocations require deliberate draining before scale-in.
    predefined_metric_specification { predefined_metric_type = "ASGAverageCPUUtilization" }
  }
}
