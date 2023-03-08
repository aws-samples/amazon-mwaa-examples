module "rds_cluster" {
  source = "../rds"

  vpc_security_group_ids    = var.vpc_security_group_ids
  vpc_id                    = var.vpc_id
  mwaa_subnet_ids           = var.mwaa_subnet_ids

}
resource "aws_ecs_cluster" "cluster" {
  name = "mwaa-local-runner-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "taskDefinition" {
  family                   = "mwaa-local-runner-task-definition"
  execution_role_arn       = var.ecs_task_execution_role_arn #role needs to have permissions to ECR as well if using existing MWAA role
  task_role_arn            = var.ecs_task_execution_role_arn
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048

  container_definitions = jsonencode([
    {
      "name"      = "mwaa-local-runner-container"
      "image"     = var.image_uri
      "essential" = true

      "entryPoint": ["/entrypoint.sh"],
      "command": [
        "local-runner"
      ],
      "linuxParameters": {
        "initProcessEnabled": true
      },
      "logConfiguration" : {
        "logDriver" : "awslogs",
        "options" : {
          "awslogs-group" : "/ecs/mwaa-local-runner-task-definition",
          "awslogs-stream-prefix" : "ecs",
          "awslogs-region": var.region
        }
      },
      "environment": [
        {"name": "AIRFLOW__CORE__SQL_ALCHEMY_CONN", "value": "postgresql+psycopg2://postgres:${module.rds_cluster.db_passsword}@${module.rds_cluster.writer_instance_endpoint}:5432/AirflowMetadata"},
        {"name": "AIRFLOW__WEBSERVER__COOKIE_SECURE", "value": "False"},
        {"name": "DEFAULT_PASSWORD", "value": "test1234"},
        {"name": "EXECUTOR", "value": "Local"},
        {"name": "S3_DAGS_PATH", "value": var.s3_dags_path},
        {"name": "S3_PLUGINS_PATH", "value": var.s3_plugins_path},
        {"name": "S3_REQUIREMENTS_PATH", "value": var.s3_requirements_path}

      ],

      "portMappings" = [
        {
          "protocol" : "tcp",
          "containerPort" = 8080
        }
      ]
    }
  ])
}

resource "aws_ecs_service" "ecsService" {
  name            = "mwaa-local-runner-service"
  cluster         = aws_ecs_cluster.cluster.id
  launch_type     = "FARGATE"
  task_definition = aws_ecs_task_definition.taskDefinition.arn

  desired_count                      = 1
  enable_ecs_managed_tags            = true

  health_check_grace_period_seconds = 10

  network_configuration {
    subnets = var.mwaa_subnet_ids 
    security_groups = var.vpc_security_group_ids
    assign_public_ip = var.assign_public_ip_to_task
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.target_group.arn
    container_name   = "mwaa-local-runner-container"
    container_port   = 8080
  }
    depends_on = [
      module.rds_cluster
  ]
}

resource "aws_lb" "loadbalancer" {
  name               = "mwaa-local-runner-alb"
  internal           = false # will create an internet-facing load balancer by default. Change this to true if internal ALB is required.
  load_balancer_type = "application"
  security_groups    = var.vpc_security_group_ids
  subnets            = var.elb_subnets

  tags = {
    Environment = "mwaa-local-runner"
  }
}

resource "aws_lb_listener" "listener" {
  load_balancer_arn = aws_lb.loadbalancer.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.target_group.arn
  }
}

resource "aws_lb_target_group" "target_group" {
  name        = "mwaa-local-runner-target"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path = "/health"
  }
} 