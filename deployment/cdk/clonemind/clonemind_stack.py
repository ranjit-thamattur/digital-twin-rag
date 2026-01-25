from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
    aws_cognito as cognito,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3_notifications as s3n,
    RemovalPolicy,
    Duration,
)
from constructs import Construct

class CloneMindStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. QA Network Infrastructure
        vpc = ec2.Vpc(self, "CloneMindVPC", 
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    map_public_ip_on_launch=True
                )
            ]
        )
        
        # 1.1 ECS Cluster with EC2 Capacity
        cluster = ecs.Cluster(self, "CloneMindCluster", vpc=vpc)
        asg = cluster.add_capacity("DefaultCapacity",
            instance_type=ec2.InstanceType("t3.medium"),
            min_capacity=1,
            max_capacity=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )
        # Critical IAM roles for ECS on EC2
        asg.role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"))
        asg.role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))
        
        vpc.add_gateway_endpoint("S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3)
        
        # 1.2 Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(self, "CloneMindALB", vpc=vpc, internet_facing=True)
        web_listener = alb.add_listener("WebListener", port=80)
        mcp_listener = alb.add_listener("McpListener", port=8080, protocol=elbv2.ApplicationProtocol.HTTP)
        tenant_listener = alb.add_listener("TenantListener", port=8000, protocol=elbv2.ApplicationProtocol.HTTP)
        qdrant_listener = alb.add_listener("QdrantListener", port=6333, protocol=elbv2.ApplicationProtocol.HTTP)

        # 2. Identity & Persistence
        user_pool = cognito.UserPool(self, "UserPool",
            user_pool_name="clonemind-users",
            self_sign_up_enabled=True,
            standard_attributes=cognito.StandardAttributes(email=cognito.StandardAttribute(required=True, mutable=True)),
            custom_attributes={"tenant_id": cognito.StringAttribute(mutable=True)},
            removal_policy=RemovalPolicy.DESTROY
        )
        user_pool.add_domain("CognitoDomain", cognito_domain=cognito.CognitoDomainOptions(domain_prefix="clonemind-auth"))
        user_pool_client = user_pool.add_client("AppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=["http://localhost:3000/oauth/callback"]
            ),
            generate_secret=True
        )

        documents_bucket = s3.Bucket(self, "CloneMindDocs", removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        tenant_table = dynamodb.Table(self, "TenantMetadata", partition_key=dynamodb.Attribute(name="tenantId", type=dynamodb.AttributeType.STRING), removal_policy=RemovalPolicy.DESTROY)

        # 3. EFS with Access Points (Ensures directories exist with correct permissions)
        file_system = efs.FileSystem(self, "CloneMindEFS", vpc=vpc, removal_policy=RemovalPolicy.DESTROY)
        
        def create_ap(id: str, path: str):
            return file_system.add_access_point(id, 
                path=path, 
                create_acl=efs.Acl(owner_gid="1000", owner_uid="1000", permissions="777"),
                posix_user=efs.PosixUser(gid="1000", uid="1000")
            )

        redis_ap = create_ap("RedisAP", "/redis")
        qdrant_ap = create_ap("QdrantAP", "/qdrant")
        webui_ap = create_ap("WebUIAP", "/openwebui")

        def create_efs_vol(name: str, ap: efs.AccessPoint):
            return ecs.Volume(name=name, efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=file_system.file_system_id,
                transit_encryption="ENABLED",
                authorization_config=ecs.AuthorizationConfig(access_point_id=ap.access_point_id, iam="ENABLED")
            ))

        redis_vol = create_efs_vol("RedisVolume", redis_ap)
        qdrant_vol = create_efs_vol("QdrantVolume", qdrant_ap)
        openwebui_vol = create_efs_vol("OpenWebUIVolume", webui_ap)

        # 4. S3 Processor
        s3_processor = _lambda.Function(self, "S3ToMcpProcessor",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline("""
import os, boto3, urllib.parse, requests
def lambda_handler(event, context):
    mcp_url = os.environ.get("MCP_URL")
    for record in event['Records']:
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        parts = key.split('/')
        if len(parts) < 3: continue
        try:
            requests.post(f"{mcp_url}/call/ingest_knowledge", json={"text": f"New document: {key}", "tenantId": parts[0], "metadata": {"s3_key": key, "personaId": parts[1]}}, timeout=5)
        except: pass
    return {'statusCode': 200}
"""),
            environment={"MCP_URL": f"http://{alb.load_balancer_dns_name}:8080"},
            vpc=vpc, allow_public_subnet=True
        )
        documents_bucket.add_event_notification(s3.EventType.OBJECT_CREATED, s3n.LambdaDestination(s3_processor))

        # 5. ECS Service Helper
        def add_service(id: str, image: str, port: int, mem=256, cpu=128, env=None, volumes=None, mounts=None):
            task_def = ecs.Ec2TaskDefinition(self, f"{id}Task", network_mode=ecs.NetworkMode.BRIDGE)
            if volumes:
                for v in volumes: task_def.add_volume(name=v.name, efs_volume_configuration=v.efs_volume_configuration)
            
            container = task_def.add_container(f"{id}Container",
                image=ecs.ContainerImage.from_asset(image) if "../../" in image else ecs.ContainerImage.from_registry(image),
                memory_limit_mib=mem, cpu=cpu, environment=env or {},
                logging=ecs.LogDrivers.aws_logs(stream_prefix=id)
            )
            container.add_port_mappings(ecs.PortMapping(container_port=port, host_port=port))
            if mounts:
                for m in mounts: container.add_mount_points(m)
            
            return ecs.Ec2Service(self, f"{id}Service", cluster=cluster, task_definition=task_def, min_healthy_percent=0)

        # 6. Deploy Services
        redis = add_service("Redis", "redis:7-alpine", 6379, 
            volumes=[redis_vol], mounts=[ecs.MountPoint(container_path="/data", source_volume="RedisVolume", read_only=False)])
        
        qdrant = add_service("Qdrant", "qdrant/qdrant:latest", 6333, mem=512,
            volumes=[qdrant_vol], mounts=[ecs.MountPoint(container_path="/qdrant/storage", source_volume="QdrantVolume", read_only=False)])

        # WebUI Task (Custom build because of sidecar)
        webui_task = ecs.Ec2TaskDefinition(self, "WebUITask", network_mode=ecs.NetworkMode.BRIDGE)
        webui_task.add_volume(name=openwebui_vol.name, efs_volume_configuration=openwebui_vol.efs_volume_configuration)
        
        webui_container = webui_task.add_container("WebUI",
            image=ecs.ContainerImage.from_asset("../../deployment/docker"),
            memory_limit_mib=1024, cpu=256,
            environment={
                "WEBUI_NAME": "CloneMind AI", "ENABLE_PIPELINE_MODE": "true", "WEBUI_AUTH": "true",
                "OAUTH_CLIENT_ID": user_pool_client.user_pool_client_id,
                "OAUTH_CLIENT_SECRET": user_pool_client.user_pool_client_secret.unsafe_unwrap(),
                "OPENID_PROVIDER_URL": f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}/.well-known/openid-configuration",
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="WebUI")
        )
        webui_container.add_port_mappings(ecs.PortMapping(container_port=8080, host_port=80)) # Map to Host 80
        webui_container.add_mount_points(ecs.MountPoint(container_path="/app/backend/data", source_volume="OpenWebUIVolume", read_only=False))

        webui_task.add_container("FileSync",
            image=ecs.ContainerImage.from_asset("../../services/file-sync"),
            memory_limit_mib=128,
            environment={"S3_BUCKET": documents_bucket.bucket_name, "TENANT_SERVICE_URL": f"http://{alb.load_balancer_dns_name}:8000"},
            logging=ecs.LogDrivers.aws_logs(stream_prefix="FileSync")
        ).add_mount_points(ecs.MountPoint(container_path="/app/backend/data", source_volume="OpenWebUIVolume", read_only=False))

        webui_service = ecs.Ec2Service(self, "WebUIService", cluster=cluster, task_definition=webui_task, min_healthy_percent=0)

        mcp_service = add_service("Mcp", "../../services/mcp-server", 8080, env={
            "QDRANT_HOST": alb.load_balancer_dns_name, "QDRANT_PORT": "6333", "TENANT_TABLE": tenant_table.table_name, "MCP_TRANSPORT": "sse"
        })

        tenant_service = add_service("Tenant", "../../services/tenant-service", 8000, env={
            "TENANT_TABLE": tenant_table.table_name, "COGNITO_USER_POOL_ID": user_pool.user_pool_id
        })

        # 7. ALB Routing & Health Checks (Lenient for QA)
        def config_tg(listener, service, port, name, container_port=None):
            tg = listener.add_targets(name, 
                port=port, protocol=elbv2.ApplicationProtocol.HTTP,
                targets=[service.load_balancer_target(container_name=f"{service.node.id.replace('Service','')}Container" if not container_port else "WebUI", container_port=container_port or port)]
            )
            tg.configure_health_check(path="/", healthy_http_codes="200-499")
            return tg

        config_tg(web_listener, webui_service, 80, "WebUITarget", 8080)
        config_tg(mcp_listener, mcp_service, 8080, "McpTarget")
        config_tg(tenant_listener, tenant_service, 8000, "TenantTarget")
        config_tg(qdrant_listener, qdrant, 6333, "QdrantTarget")

        # 8. Final Security Rules
        instance_sg = asg.connections.security_groups[0]
        instance_sg.add_ingress_rule(alb.connections.security_groups[0], ec2.Port.all_tcp(), "Allow ALL from ALB")
        for p in [80, 8080, 8000, 6333, 6379]:
            instance_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(p), f"QA Port {p}")
        
        file_system.connections.allow_default_port_from(instance_sg)

        # Permissions
        documents_bucket.grant_read_write(webui_task.task_role)
        mcp_service.task_definition.task_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"]))
        file_system.grant_root_access(webui_task.task_role)
        file_system.grant_root_access(qdrant.task_definition.task_role)
        file_system.grant_root_access(redis.task_definition.task_role)
        tenant_table.grant_read_write_data(mcp_service.task_definition.task_role)
        tenant_table.grant_read_write_data(tenant_service.task_definition.task_role)
        tenant_service.task_definition.task_role.add_to_policy(iam.PolicyStatement(actions=["cognito-idp:*"], resources=[user_pool.user_pool_arn]))
