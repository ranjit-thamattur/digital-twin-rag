from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_efs as efs,
    aws_servicediscovery as servicediscovery,
    aws_cognito as cognito,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3_notifications as s3n,
    RemovalPolicy,
)
from constructs import Construct

class CloneMindStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. QA Network Infrastructure (EC2 based for cost control)
        vpc = ec2.Vpc(self, "CloneMindVPC", max_azs=1)
        
        # ECS Cluster with EC2 Capacity
        cluster = ecs.Cluster(self, "CloneMindCluster", vpc=vpc)
        cluster.add_capacity("DefaultCapacity",
            instance_type=ec2.InstanceType("t3.micro"),
            min_capacity=1,
            max_capacity=2
        )
        
        # Add Service Discovery Namespace
        namespace = cluster.add_default_cloud_map_namespace(
            name="clonemind.local",
            type=servicediscovery.NamespaceType.DNS_PRIVATE
        )

        # 2. AWS Cognito for Managed Identity
        user_pool = cognito.UserPool(self, "UserPool",
            user_pool_name="clonemind-users",
            self_sign_up_enabled=True,
            signInCaseSensitive=False,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True)
            ),
            custom_attributes={
                "tenant_id": cognito.StringAttribute(mutable=True)
            },
            removal_policy=RemovalPolicy.DESTROY
        )

        user_pool_domain = user_pool.add_domain("CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix="clonemind-auth"
            )
        )

        user_pool_client = user_pool.add_client("AppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=["http://localhost:3000/oauth/callback"] 
            ),
            generate_secret=True
        )

        # 3. Persistence Layer
        documents_bucket = s3.Bucket(self, "CloneMindDocs",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        tenant_table = dynamodb.Table(self, "TenantMetadata",
            partition_key=dynamodb.Attribute(name="tenantId", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # 4. EFS for Shared Persistence
        file_system = efs.FileSystem(self, "CloneMindEFS",
            vpc=vpc,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Volume Definitions
        redis_vol = ecs.Volume(name="RedisVolume", efs_volume_configuration=ecs.EfsVolumeConfiguration(file_system_id=file_system.file_system_id))
        qdrant_vol = ecs.Volume(name="QdrantVolume", efs_volume_configuration=ecs.EfsVolumeConfiguration(file_system_id=file_system.file_system_id))
        openwebui_vol = ecs.Volume(name="OpenWebUIVolume", efs_volume_configuration=ecs.EfsVolumeConfiguration(file_system_id=file_system.file_system_id))

        # 5. S3 Processor Lambda
        s3_processor = _lambda.Function(self, "S3ToMcpProcessor",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline("""
import json
import boto3
import urllib.parse
import os
import requests

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    mcp_url = os.environ.get("MCP_URL")
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        # Extract from path: tenant_id/persona_id/filename
        parts = key.split('/')
        if len(parts) < 3: continue
        tenant_id, persona_id = parts[0], parts[1]
        
        # Ingest into MCP Knowledge Base
        try:
            requests.post(
                f"{mcp_url}/call/ingest_knowledge",
                json={
                    "text": f"New document uploaded: {key}",
                    "tenantId": tenant_id,
                    "metadata": {"s3_key": key, "personaId": persona_id}
                },
                timeout=10
            )
        except Exception as e:
            print(f"Error calling MCP: {e}")
            
    return {'statusCode': 200}
            """),
            environment={
                "MCP_URL": "http://mcp.clonemind.local:8080" 
            },
            vpc=vpc
        )
        documents_bucket.add_event_notification(s3.EventType.OBJECT_CREATED, s3n.LambdaDestination(s3_processor))

        # 6. ECS Services (EC2 Mode with BRIDGE Networking for Direct IP)
        def add_ec2_service(id: str, image_asset: str, container_port: int, host_port: int, cpu=128, mem=256, env=None, volumes=None, mounts=None):
            # Using BRIDGE mode to map container ports to specific host ports
            task_def = ecs.Ec2TaskDefinition(self, f"{id}Task", network_mode=ecs.NetworkMode.BRIDGE)
            if volumes: 
                for v in volumes: task_def.add_volume(v)
            
            container = task_def.add_container(f"{id}Container",
                image=ecs.ContainerImage.from_asset(image_asset) if "../../" in image_asset else ecs.ContainerImage.from_registry(image_asset),
                memory_limit_mib=mem,
                cpu=cpu,
                environment=env or {},
                logging=ecs.LogDrivers.aws_logs(stream_prefix=id)
            )
            container.add_port_mappings(ecs.PortMapping(container_port=container_port, host_port=host_port))
            if mounts:
                for m in mounts: container.add_mount_points(m)

            service = ecs.Ec2Service(self, f"{id}Service",
                cluster=cluster,
                task_definition=task_def,
                cloud_map_options=ecs.CloudMapOptions(name=id.lower())
            )
            return service

        # Infrastructure Services
        redis = add_ec2_service("Redis", "redis:7-alpine", 6379, 6379, env={}, 
            volumes=[redis_vol], mounts=[ecs.MountPoint(container_path="/data", source_volume="RedisVolume", read_only=False)])
        
        qdrant = add_ec2_service("Qdrant", "qdrant/qdrant:latest", 6333, 6333, env={},
            volumes=[qdrant_vol], mounts=[ecs.MountPoint(container_path="/qdrant/storage", source_volume="QdrantVolume", read_only=False)])

        # Application Services
        # 1. Open WebUI + Sidecar (Map Container 8080 -> Host 80 for easy access)
        webui_task = ecs.Ec2TaskDefinition(self, "WebUITask", network_mode=ecs.NetworkMode.BRIDGE)
        webui_task.add_volume(openwebui_vol)
        
        webui_container = webui_task.add_container("WebUI",
            image=ecs.ContainerImage.from_asset("../../deployment/docker"),
            memory_limit_mib=512,
            environment={
                "WEBUI_NAME": "CloneMind AI",
                "ENABLE_PIPELINE_MODE": "true",
                "WEBUI_AUTH": "true",
                "OAUTH_CLIENT_ID": user_pool_client.user_pool_client_id,
                "OAUTH_CLIENT_SECRET": user_pool_client.user_pool_client_secret.unsafe_unwrap(),
                "OPENID_PROVIDER_URL": f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}/.well-known/openid-configuration",
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="WebUI")
        )
        webui_container.add_port_mappings(ecs.PortMapping(container_port=8080, host_port=80))
        webui_container.add_mount_points(ecs.MountPoint(container_path="/app/backend/data", source_volume="OpenWebUIVolume", read_only=False))

        sync_container = webui_task.add_container("FileSyncSidecar",
            image=ecs.ContainerImage.from_asset("../../services/file-sync"),
            memory_limit_mib=128,
            environment={
                "S3_BUCKET": documents_bucket.bucket_name,
                "AWS_DEFAULT_REGION": self.region,
                "TENANT_SERVICE_URL": "http://webui.clonemind.local:8000" # Internal routing
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="FileSync")
        )
        sync_container.add_mount_points(ecs.MountPoint(container_path="/app/backend/data", source_volume="OpenWebUIVolume", read_only=False))

        webui_service = ecs.Ec2Service(self, "WebUIService", 
            cluster=cluster, task_definition=webui_task,
            cloud_map_options=ecs.CloudMapOptions(name="webui")
        )

        # 2. MCP Server (8080 -> 8080)
        mcp_service = add_ec2_service("Mcp", "../../services/mcp-server", 8080, 8080, env={
            "AWS_DEFAULT_REGION": self.region,
            "QDRANT_HOST": "qdrant.clonemind.local",
            "MCP_TRANSPORT": "sse"
        })

        # 3. Tenant Service (8000 -> 8000)
        tenant_service = add_ec2_service("Tenant", "../../services/tenant-service", 8000, 8000, env={
            "TENANT_TABLE": tenant_table.table_name,
            "AWS_DEFAULT_REGION": self.region
        })

        # --- Security Group Configuration for Direct Access ---
        # Allow public access to specific ports since the ALB is gone
        security_group = cluster.connections.security_groups[0]
        security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "OpenWebUI Dashboard")
        security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8000), "Tenant Service Portal")
        security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8080), "MCP Server API")
        security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(6333), "Qdrant Dashboard")

        # 7. Permissions
        documents_bucket.grant_read_write(webui_task.task_role)
        mcp_service.task_definition.task_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"]))
        file_system.grant_root_access(webui_task.task_role)
        file_system.grant_root_access(qdrant.task_definition.task_role)
        file_system.grant_root_access(redis.task_definition.task_role)
        tenant_table.grant_read_write_data(mcp_service.task_definition.task_role)
        tenant_table.grant_read_write_data(tenant_service.task_definition.task_role)
        
        # Grant Tenant Service Cognito permissions
        tenant_service.task_definition.task_role.add_to_policy(iam.PolicyStatement(
            actions=["cognito-idp:*"],
            resources=[user_pool.user_pool_arn]
        ))

