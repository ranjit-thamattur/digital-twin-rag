import os
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
    aws_s3_notifications as s3n,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    SecretValue,
    RemovalPolicy,
    Duration,
    CfnOutput,
)
from constructs import Construct

class CloneMindStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ===================================================================
        # 1. NETWORK INFRASTRUCTURE - SINGLE AZ
        # ===================================================================
        vpc = ec2.Vpc(self, "CloneMindVPCV2", 
            max_azs=1,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    map_public_ip_on_launch=True
                )
            ]
        )
        
        vpc.add_gateway_endpoint("S3Endpoint", 
            service=ec2.GatewayVpcEndpointAwsService.S3
        )
        
        # ===================================================================
        # 2. ECS CLUSTER WITH EC2 CAPACITY
        # ===================================================================
        cluster = ecs.Cluster(self, "CloneMindClusterV2", 
            vpc=vpc,
            cluster_name="clonemind-cluster"
        )
        
        asg = cluster.add_capacity("FinalCapacity",
            instance_type=ec2.InstanceType("t3.medium"),
            key_name="cloud mind",
            min_capacity=1,
            max_capacity=1,
            desired_capacity=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            associate_public_ip_address=True
        )
        
        asg.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonEC2ContainerServiceforEC2Role"
            )
        )
        asg.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )

        # ===================================================================
        # 3. COGNITO USER POOL
        # ===================================================================
        user_pool = cognito.UserPool(self, "UserPool",
            user_pool_name="clonemind-users",
            self_sign_up_enabled=True,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True)
            ),
            custom_attributes={
                "tenant_id": cognito.StringAttribute(mutable=True)
            },
            removal_policy=RemovalPolicy.DESTROY
        )
        
        user_pool.add_domain("CognitoDomain", 
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"clonemind-{self.account}"
            )
        )
        
        webui_client = user_pool.add_client("WebUIClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID, 
                    cognito.OAuthScope.EMAIL, 
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    "http://localhost:8080/oauth/callback",
                    "http://localhost:8080/oauth/oidc/callback"
                ]
            ),
            generate_secret=True
        )
        
        admin_client = user_pool.add_client("AdminClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID, 
                    cognito.OAuthScope.EMAIL, 
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    "http://localhost:8000/oauth/callback"
                ]
            ),
            generate_secret=True
        )

        # ===================================================================
        # 4. STORAGE: S3 & DYNAMODB
        # ===================================================================
        documents_bucket = s3.Bucket(self, "CloneMindDocs", 
            removal_policy=RemovalPolicy.DESTROY, 
            auto_delete_objects=True,
            bucket_name=f"clonemind-docs-{self.account}"
        )
        
        tenant_table = dynamodb.Table(self, "TenantMetadata", 
            partition_key=dynamodb.Attribute(
                name="tenantId", 
                type=dynamodb.AttributeType.STRING
            ), 
            removal_policy=RemovalPolicy.DESTROY,
            table_name="clonemind-tenants"
        )

        # ===================================================================
        # 5. EFS WITH ACCESS POINTS
        # ===================================================================
        file_system = efs.FileSystem(self, "CloneMindEFS", 
            vpc=vpc, 
            removal_policy=RemovalPolicy.DESTROY,
            file_system_name="clonemind-efs"
        )
        
        def create_access_point(id: str, path: str):
            return file_system.add_access_point(id, 
                path=path, 
                create_acl=efs.Acl(
                    owner_gid="0",
                    owner_uid="0",
                    permissions="777"
                )
            )

        webui_ap = create_access_point("WebUIAP", "/openwebui")

        # ===================================================================
        # 6. REDIS SERVICE
        # ===================================================================
        redis_task = ecs.Ec2TaskDefinition(self, "RedisTask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        redis_container = redis_task.add_container("RedisContainer",
            image=ecs.ContainerImage.from_registry("redis:7-alpine"),
            memory_limit_mib=256,
            cpu=128,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Redis")
        )
        redis_container.add_port_mappings(
            ecs.PortMapping(container_port=6379, host_port=6379)
        )
        
        redis_service = ecs.Ec2Service(self, "RedisService", 
            cluster=cluster, 
            task_definition=redis_task,
            desired_count=1,
            min_healthy_percent=0,
            max_healthy_percent=100,
            service_name="redis"
        )

        # ===================================================================
        # 7. QDRANT SERVICE
        # ===================================================================
        qdrant_task = ecs.Ec2TaskDefinition(self, "QdrantTask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        qdrant_container = qdrant_task.add_container("QdrantContainer",
            image=ecs.ContainerImage.from_registry("qdrant/qdrant:latest"),
            memory_limit_mib=768,
            cpu=256,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Qdrant")
        )
        qdrant_container.add_port_mappings(
            ecs.PortMapping(container_port=6333, host_port=6333),
            ecs.PortMapping(container_port=6334, host_port=6334)
        )
        
        qdrant_service = ecs.Ec2Service(self, "QdrantService", 
            cluster=cluster, 
            task_definition=qdrant_task,
            desired_count=1,
            min_healthy_percent=0,
            max_healthy_percent=100,
            service_name="qdrant"
        )

        # ===================================================================
        # 8. MCP SERVER SERVICE - UPDATED FOR OPENAI
        # ===================================================================
        
        # Environment variables for MCP
        mcp_env = {
            "QDRANT_HOST": "172.17.0.1",
            "QDRANT_PORT": "6333",
            "TENANT_TABLE": tenant_table.table_name,
            "MCP_TRANSPORT": "sse",
            "AWS_REGION": self.region,
            "PORT": "3000",
            "EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "")
        }
        
        mcp_task = ecs.Ec2TaskDefinition(self, "McpTask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        mcp_container = mcp_task.add_container("McpContainer",
            image=ecs.ContainerImage.from_asset("../../services/mcp-server"),
            memory_limit_mib=512,  # Increased for better performance
            cpu=256,               # Increased for better performance
            environment=mcp_env,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Mcp")
        )
        mcp_container.add_port_mappings(
            ecs.PortMapping(container_port=3000, host_port=3000)
        )
        
        tenant_table.grant_read_write_data(mcp_task.task_role)
        
        # REMOVED: No longer using Bedrock
        # mcp_task.task_role.add_to_policy(
        #     iam.PolicyStatement(
        #         actions=["bedrock:InvokeModel"],
        #         resources=["*"]
        #     )
        # )
        
        mcp_service = ecs.Ec2Service(self, "McpService", 
            cluster=cluster, 
            task_definition=mcp_task,
            desired_count=1,
            min_healthy_percent=0,
            service_name="mcp-server"
        )

        # ===================================================================
        # 9. TENANT SERVICE
        # ===================================================================
        tenant_task = ecs.Ec2TaskDefinition(self, "TenantTask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        tenant_container = tenant_task.add_container("TenantContainer",
            image=ecs.ContainerImage.from_asset("../../services/tenant-service"),
            memory_limit_mib=192,
            cpu=64,
            environment={
                "TENANT_TABLE": tenant_table.table_name,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": admin_client.user_pool_client_id,
                "AWS_REGION": self.region
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Tenant")
        )
        tenant_container.add_port_mappings(
            ecs.PortMapping(container_port=8000, host_port=8000)
        )
        
        tenant_table.grant_read_write_data(tenant_task.task_role)
        tenant_task.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:*"],
                resources=[user_pool.user_pool_arn]
            )
        )
        
        tenant_service = ecs.Ec2Service(self, "TenantService", 
            cluster=cluster, 
            task_definition=tenant_task,
            desired_count=1,
            min_healthy_percent=0,
            service_name="tenant-service"
        )

        # ===================================================================
        # 10. WEBUI SERVICE
        # ===================================================================
        webui_task = ecs.Ec2TaskDefinition(self, "WebUITask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        webui_task.add_volume(
            name="OpenWebUIVolume",
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=file_system.file_system_id,
                transit_encryption="ENABLED",
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=webui_ap.access_point_id,
                    iam="ENABLED"
                )
            )
        )
        
        webui_container = webui_task.add_container("WebUI",
            image=ecs.ContainerImage.from_asset("../docker"),
            memory_limit_mib=1536,
            cpu=256,
            environment={
                "WEBUI_NAME": "Peak AI 1.0",
                "ENABLE_PIPELINE_MODE": "true",
                "WEBUI_AUTH": "true",
                "ENABLE_SIGNUP": "true",
                "ENABLE_OAUTH_SIGNUP": "true",
                "DEFAULT_USER_ROLE": "user",
                "PORT": "8080",
                "OAUTH_CLIENT_ID": webui_client.user_pool_client_id,
                "OAUTH_CLIENT_SECRET": webui_client.user_pool_client_secret.unsafe_unwrap(),
                "OPENID_PROVIDER_URL": f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}/.well-known/openid-configuration",
                "REDIRECT_URI": "http://localhost:8080/oauth/oidc/callback",
                "WEBUI_FAVICON_URL": "/static/peak_logo.png",
                "WEBUI_LOGO_URL": "/static/peak_logo.png",
                "DEPLOYMENT_ID": "v6-nuclear-branding",
                "DEPLOY_TIMESTAMP": "2026-02-02-1545",
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="WebUI")
        )
        webui_container.add_port_mappings(
            ecs.PortMapping(container_port=8080, host_port=8080)
        )
        webui_container.add_mount_points(
            ecs.MountPoint(
                container_path="/app/backend/data", 
                source_volume="OpenWebUIVolume", 
                read_only=False
            )
        )
        
        filesync_container = webui_task.add_container("FileSync",
            image=ecs.ContainerImage.from_asset("../../services/file-sync"),
            memory_limit_mib=192,
            cpu=64,
            environment={
                "S3_BUCKET": documents_bucket.bucket_name,
                "TENANT_SERVICE_URL": "http://172.17.0.1:8000"
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="FileSync")
        )
        filesync_container.add_mount_points(
            ecs.MountPoint(
                container_path="/app/backend/data", 
                source_volume="OpenWebUIVolume", 
                read_only=False
            )
        )
        
        documents_bucket.grant_read_write(webui_task.task_role)
        file_system.grant_root_access(webui_task.task_role)
        
        webui_service = ecs.Ec2Service(self, "WebUIService", 
            cluster=cluster, 
            task_definition=webui_task,
            desired_count=1,
            min_healthy_percent=0,
            service_name="webui"
        )

        # ===================================================================
        # 11. S3 PROCESSOR LAMBDA
        # ===================================================================
        s3_processor = _lambda.Function(self, "S3ToMcpProcessor",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline("""
import os, boto3, urllib.parse, urllib.request, json, time

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    mcp_url = os.environ.get("MCP_URL")
    
    if not mcp_url:
        print("CRITICAL: MCP_URL not configured in environment variables")
        return {'statusCode': 500, 'body': 'MCP_URL not set'}
    
    print(f"Starting ingestion process. MCP URL: {mcp_url}")
    
    for record in event.get('Records', []):
        try:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            parts = key.split('/')
            
            if len(parts) < 3:
                print(f"Skipping {key}: path does not follow 'tenant/persona/file' structure")
                continue
            
            tenant_id = parts[0]
            persona_id = parts[1]
            filename = parts[-1]
            
            print(f"Processing knowledge: s3://{bucket}/{key} for tenant: {tenant_id}")
            
            response = s3.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8', errors='ignore')
            
            if not content:
                print(f"Warning: File {key} is empty")
                continue

            payload = {
                "text": content[:250000], 
                "tenantId": tenant_id,
                "metadata": {
                    "filename": filename,
                    "s3_key": key,
                    "personaId": persona_id,
                    "ingested_at": int(time.time())
                }
            }
            
            print(f"Sending {len(payload['text'])} characters to MCP server...")
            
            req = urllib.request.Request(
                f"{mcp_url}/call/ingest_knowledge",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            try:
                with urllib.request.urlopen(req, timeout=110) as response:
                    resp_body = response.read().decode('utf-8')
                    print(f"Successfully processed {key}. MCP Response: {resp_body}")
            except Exception as req_err:
                print(f"Request to MCP failed for {key}: {str(req_err)}")
            
        except Exception as e:
            print(f"Unexpected error processing {key}: {str(e)}")
            continue
    
    return {'statusCode': 200, 'body': json.dumps('Processed all records')}
"""),
            environment={
                "MCP_URL": ""  # Update after deployment: http://EC2_IP:3000
            },
            timeout=Duration.seconds(180),
            memory_size=512
        )
        
        documents_bucket.grant_read(s3_processor)
        
        documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(s3_processor)
        )

        # ===================================================================
        # 12. SECURITY GROUPS
        # ===================================================================
        instance_sg = asg.connections.security_groups[0]
        
        for port in [8080, 3000, 8000, 6333, 6334, 6379]:
            instance_sg.add_ingress_rule(
                ec2.Peer.any_ipv4(),
                ec2.Port.tcp(port),
                f"Public Access Port {port}"
            )
        
        file_system.connections.allow_default_port_from(instance_sg)

        # ===================================================================
        # 13. OUTPUTS
        # ===================================================================
        CfnOutput(self, "EC2InstanceInfo",
            value="aws ec2 describe-instances --filters 'Name=tag:aws:autoscaling:groupName,Values=*FinalCapacity*' --query 'Reservations[0].Instances[0].PublicIpAddress' --output text",
            description="Command to get EC2 Public IP"
        )
        
        CfnOutput(self, "ServiceEndpoints",
            value="WebUI=http://EC2_IP:8080, Qdrant=http://EC2_IP:6333, MCP=http://EC2_IP:3000, Tenant=http://EC2_IP:8000",
            description="Service Access URLs"
        )
        
        CfnOutput(self, "PostDeploymentSteps",
            value="1. Get EC2 IP. 2. Update Cognito callback to http://EC2_IP:8080/oauth/callback. 3. Update Lambda MCP_URL to http://EC2_IP:3000",
            description="Manual steps after deployment"
        )
        
        CfnOutput(self, "S3BucketName", value=documents_bucket.bucket_name)
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "WebUIClientId", value=webui_client.user_pool_client_id)
        CfnOutput(self, "AdminClientId", value=admin_client.user_pool_client_id)
        CfnOutput(self, "LambdaFunctionName", value=s3_processor.function_name)
        
        # New output for OpenAI setup
        CfnOutput(self, "OpenAiProvider",
            value="Active (via Environment Variable)",
            description="Status of OpenAI Provider"
        )