data "aws_ssm_parameter" "ubuntu" {
  count = local.utility_needed ? 1 : 0
  name  = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
}
resource "aws_security_group" "utility" {
  name_prefix = "${var.name_prefix}-utility-"
  vpc_id      = aws_vpc.demo.id
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = aws_subnet.private[*].cidr_block
  }
  dynamic "ingress" {
    for_each = var.enable_turn ? { tcp = "tcp", udp = "udp" } : {}
    content {
      from_port   = 3478
      to_port     = 3478
      protocol    = ingress.value
      cidr_blocks = ["0.0.0.0/0"]
    }
  }
  dynamic "ingress" {
    for_each = var.enable_turn ? [1] : []
    content {
      from_port   = 49160
      to_port     = 49200
      protocol    = "udp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_eip" "utility" {
  count  = local.utility_needed ? 1 : 0
  domain = "vpc"
}
resource "aws_iam_role" "utility" {
  count              = local.utility_needed ? 1 : 0
  name               = "${var.name_prefix}-utility"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }] })
}
resource "aws_iam_role_policy_attachment" "utility_ssm" {
  count      = local.utility_needed ? 1 : 0
  role       = aws_iam_role.utility[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "utility_secret" {
  count  = local.utility_needed ? 1 : 0
  role   = aws_iam_role.utility[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = aws_secretsmanager_secret.config["turn"].arn }] })
}
resource "aws_iam_instance_profile" "utility" {
  count = local.utility_needed ? 1 : 0
  name  = "${var.name_prefix}-utility"
  role  = aws_iam_role.utility[0].name
}
resource "aws_instance" "utility" {
  count                       = local.utility_needed ? 1 : 0
  ami                         = data.aws_ssm_parameter.ubuntu[0].value
  instance_type               = "t4g.nano"
  subnet_id                   = aws_subnet.public[0].id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.utility.id]
  iam_instance_profile        = aws_iam_instance_profile.utility[0].name
  source_dest_check           = false
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/utility.sh.tftpl", {
    nat_enabled  = var.egress_mode == "instance"
    turn_enabled = var.enable_turn
    secret_arn   = jsonencode(aws_secretsmanager_secret.config["turn"].arn)
    realm        = jsonencode(var.origin_hostname)
    public_ip    = jsonencode(aws_eip.utility[0].public_ip)
  })
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    encrypted             = true
    delete_on_termination = true
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  credit_specification { cpu_credits = "standard" }
  tags       = { Name = "${var.name_prefix}-nat-turn" }
  depends_on = [aws_route.internet, aws_iam_role_policy.utility_secret]
}
resource "aws_eip_association" "utility" {
  count         = local.utility_needed ? 1 : 0
  instance_id   = aws_instance.utility[0].id
  allocation_id = aws_eip.utility[0].id
}
