
locals  {
  azs = slice(data.aws_availability_zones.available.names,0,2)
  account = data.aws_caller_identity.current.account_id

  widgets =  [
        {
            "height": 6,
            "width": 8,
            "y": 0,
            "x": 0,
            "type": "metric",
            "properties": {
                "metrics": [
                    [ "AWS/MWAA", "CPUUtilization", "Environment", var.name, "Cluster", "AdditionalWorker" ],
                    [ "...", "BaseWorker" ]
                ],
                "sparkline": true,
                "view": "timeSeries",
                "stacked": true,
                "region":data.aws_region.current.id,
                "stat": "SampleCount",
                "period": 60,
                "title": "Worker count"
            }
        },
        {
            "height": 12,
            "width": 24,
            "y": 6,
            "x": 0,
            "type": "metric",
            "properties": {
                "metrics": [
                    [ "AWS/MWAA", "CPUUtilization", "Environment", var.name, "Cluster", "AdditionalWorker", { "visible": false } ],
                    [ "AWS/MWAA", "MemoryUtilization", ".", ".", ".", ".", { "visible": false } ],
                    [ ".", "CPUUtilization", ".", var.name, ".", "BaseWorker" ],
                    [ ".", "MemoryUtilization", ".", ".", ".", "." ],
                    [ "...", "AdditionalWorker" ],
                    [ ".", "CPUUtilization", ".", ".", ".", "." ],
                    [ "...", "Scheduler" ],
                    [ ".", "MemoryUtilization", ".", ".", ".", "." ]
                ],
                "sparkline": true,
                "region":data.aws_region.current.id,
                "view": "gauge",
                "stacked": false,
                "stat": "Maximum",
                "period": 60,
                "yAxis": {
                    "left": {
                        "min": 0,
                        "max": 80
                    }
                },
               "setPeriodToTimeRange": false,
                "trend": true,
                "liveData": true,
                "title": "CPUUtilization, MemoryUtilization"
            }
        },
        {
            "height": 6,
            "width": 8,
            "y": 0,
            "x": 16,
            "type": "metric",
            "properties": {
                "view": "timeSeries",
                "region":data.aws_region.current.id,
                "stacked": false,
                "metrics": [
                    [ "AWS/MWAA", "ApproximateAgeOfOldestTask", "Environment", var.name ]
                ],
               "title": "Queue - ApproximateAgeOfOldestTask"
            }
        },
        {
            "height": 6,
            "width": 8,
            "y": 18,
            "x": 0,
            "type": "metric",
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "title": "DatabaseConnections",
                "region":data.aws_region.current.id,
                "stat": "Average",
                "period": 300,
                "metrics": [
                    [ "AWS/MWAA", "DatabaseConnections", "DatabaseRole", "WRITER", "Environment", var.name ]
                ]
            }
        },
        {
            "height": 6,
            "width": 8,
            "y": 18,
            "x": 8,
            "type": "metric",
            "properties": {
                "view": "gauge",
                "stacked": false,
                "title": "Database CPU Utilization",
                "stat": "Average",
                "period": 300,
                "region":data.aws_region.current.id,
                "yAxis": {
                    "left": {
                        "max": 80,
                        "min": 0
                    }
                },
                "metrics": [
                    [ "AWS/MWAA", "CPUUtilization", "DatabaseRole", "WRITER", "Environment", var.name ]
                ]
            }
        },
        {
            "height": 6,
            "width": 8,
            "y": 18,
            "x": 16,
            "type": "metric",
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "title": "Database Freeable memory",
                "stat": "Average",
                "region":data.aws_region.current.id,
                "period": 300,
                "yAxis": {
                    "left": {
                        "showUnits": false
                    }
                },
                "metrics": [
                    [ "AWS/MWAA", "FreeableMemory", "DatabaseRole", "WRITER", "Environment", var.name ]
                ]
            }
        },
        {
            "type": "metric",
            "x": 8,
            "y": 0,
            "width": 8,
            "height": 6,
            "properties": {
                "metrics": [
                    [ "AWS/MWAA", "RunningTasks", "Environment", var.name ],
                    [ ".", "QueuedTasks", ".", "." ]
                ],
                "view": "timeSeries",
                "stacked": true,
                "region": data.aws_region.current.id,
                "start": "-PT168H",
                "end": "P0D",
                "stat": "Maximum",
                "period": 300,
                "title": "Queue - QueuedTasks, RunningTasks"
            }
        }
    ]

}
