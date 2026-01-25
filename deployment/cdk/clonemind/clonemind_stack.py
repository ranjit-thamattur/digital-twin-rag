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
        vpc = ec2.Vpc(self, "CloneMindVPC", 
            max_azs=1,  # SIMPLIFIED: Single AZ for QA
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    map_public_ip_on_launch=True
                )
            ]
        )
        
        # S3 Gateway Endpoint (free, improves performance)
        vpc.add_gateway_endpoint("S3Endpoint", 
            service=ec2.GatewayVpcEndpointAwsService.S3
        )
        
        # ===================================================================
        # 2. ECS CLUSTER WITH EC2 CAPACITY
        # ===================================================================
        cluster = ecs.Cluster(self, "CloneMindCluster", 
            vpc=vpc,
            cluster_name="clonemind-cluster"
        )
        
        # Add EC2 capacity - t3.medium for QA with public IP
        asg = cluster.add_capacity("DefaultCapacity",
            instance_type=ec2.InstanceType("t3.medium"),
            min_capacity=1,
            max_capacity=1,  # SIMPLIFIED: Single instance for QA
            desired_capacity=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            associate_public_ip_address=True  # CRITICAL: Ensure public IP
        )
        
        # CRITICAL: ECS Agent needs these permissions
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
        # 3. COGNITO USER POOL - Dynamic EC2 IP Handling
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
        
        # Note: You'll need to update callback URLs manually after deployment with EC2 IP
        user_pool_client = user_pool.add_client("AppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID, 
                    cognito.OAuthScope.EMAIL, 
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    "http://localhost:3000/oauth/callback"  # Placeholder - update after deployment
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
                    owner_gid="1000", 
                    owner_uid="1000", 
                    permissions="777"
                ),
                posix_user=efs.PosixUser(gid="1000", uid="1000")
            )

        redis_ap = create_access_point("RedisAP", "/redis")
        qdrant_ap = create_access_point("QdrantAP", "/qdrant")
        webui_ap = create_access_point("WebUIAP", "/openwebui")

        # ===================================================================
        # 6. REDIS SERVICE
        # ===================================================================
        redis_task = ecs.Ec2TaskDefinition(self, "RedisTask", 
            network_mode=ecs.NetworkMode.HOST  # HOST mode for direct access
        )
        
        redis_task.add_volume(
            name="RedisVolume",
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=file_system.file_system_id,
                transit_encryption="ENABLED",
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=redis_ap.access_point_id,
                    iam="ENABLED"
                )
            )
        )
        
        redis_container = redis_task.add_container("RedisContainer",
            image=ecs.ContainerImage.from_registry("redis:7-alpine"),
            memory_limit_mib=128,
            cpu=64,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Redis")
        )
        redis_container.add_port_mappings(
            ecs.PortMapping(container_port=6379)  # HOST mode - no host port needed
        )
        redis_container.add_mount_points(
            ecs.MountPoint(
                container_path="/data", 
                source_volume="RedisVolume", 
                read_only=False
            )
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
            network_mode=ecs.NetworkMode.HOST
        )
        
        qdrant_task.add_volume(
            name="QdrantVolume",
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=file_system.file_system_id,
                transit_encryption="ENABLED",
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=qdrant_ap.access_point_id,
                    iam="ENABLED"
                )
            )
        )
        
        qdrant_container = qdrant_task.add_container("QdrantContainer",
            image=ecs.ContainerImage.from_registry("qdrant/qdrant:latest"),
            memory_limit_mib=512,
            cpu=128,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Qdrant"),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:6333/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60)
            )
        )
        qdrant_container.add_port_mappings(
            ecs.PortMapping(container_port=6333)
        )
        qdrant_container.add_mount_points(
            ecs.MountPoint(
                container_path="/qdrant/storage", 
                source_volume="QdrantVolume", 
                read_only=False
            )
        )
        
        file_system.grant_root_access(qdrant_task.task_role)
        
        qdrant_service = ecs.Ec2Service(self, "QdrantService", 
            cluster=cluster, 
            task_definition=qdrant_task,
            desired_count=1,
            min_healthy_percent=0,
            max_healthy_percent=100,
            service_name="qdrant"
        )

        # ===================================================================
        # 8. MCP SERVER SERVICE  
        # ===================================================================
        mcp_task = ecs.Ec2TaskDefinition(self, "McpTask", 
            network_mode=ecs.NetworkMode.HOST
        )
        
        mcp_container = mcp_task.add_container("McpContainer",
            image=ecs.ContainerImage.from_asset("../../services/mcp-server"),
            memory_limit_mib=384,
            cpu=128,
            environment={
                "QDRANT_HOST": "localhost",  # Same host with HOST network mode
                "QDRANT_PORT": "6333",
                "TENANT_TABLE": tenant_table.table_name,
                "MCP_TRANSPORT": "sse",
                "AWS_REGION": self.region
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Mcp")
        )
        mcp_container.add_port_mappings(
            ecs.PortMapping(container_port=8080)
        )
        
        tenant_table.grant_read_write_data(mcp_task.task_role)
        mcp_task.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"]
            )
        )
        
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
            network_mode=ecs.NetworkMode.HOST
        )
        
        tenant_container = tenant_task.add_container("TenantContainer",
            image=ecs.ContainerImage.from_asset("../../services/tenant-service"),
            memory_limit_mib=192,
            cpu=64,
            environment={
                "TENANT_TABLE": tenant_table.table_name,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "AWS_REGION": self.region
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Tenant")
        )
        tenant_container.add_port_mappings(
            ecs.PortMapping(container_port=8000)
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
            network_mode=ecs.NetworkMode.HOST
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
            image=ecs.ContainerImage.from_asset("../../deployment/docker"),
            memory_limit_mib=1536,
            cpu=256,
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
        webui_container.add_port_mappings(
            ecs.PortMapping(container_port=8080)  # WebUI runs on 8080
        )
        webui_container.add_mount_points(
            ecs.MountPoint(
                container_path="/app/backend/data", 
                source_volume="OpenWebUIVolume", 
                read_only=False
            )
        )
        
        # Sidecar: File sync container
        filesync_container = webui_task.add_container("FileSync",
            image=ecs.ContainerImage.from_asset("../../services/file-sync"),
            memory_limit_mib=192,
            cpu=64,
            environment={
                "S3_BUCKET": documents_bucket.bucket_name,
                "TENANT_SERVICE_URL": "http://localhost:8000"  # Same host
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
        # Note: Lambda will need to be updated with EC2 IP after deployment
        s3_processor = _lambda.Function(self, "S3ToMcpProcessor",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline("""
import os, boto3, urllib.parse, requests, json

def lambda_handler(event, context):
    mcp_url = os.environ.get("MCP_URL")
    
    if not mcp_url:
        print("MCP_URL not configured")
        return {'statusCode': 200, 'body': json.dumps('MCP_URL not set')}
    
    for record in event.get('Records', []):
        try:
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            parts = key.split('/')
            
            if len(parts) < 3:
                print(f"Skipping {key}: insufficient path parts")
                continue
            
            tenant_id = parts[0]
            persona_id = parts[1]
            
            print(f"Processing: {key} -> tenant={tenant_id}, persona={persona_id}")
            
            response = requests.post(
                f"{mcp_url}/call/ingest_knowledge",
                json={
                    "text": f"New document uploaded: {key}",
                    "tenantId": tenant_id,
                    "metadata": {
                        "s3_key": key,
                        "personaId": persona_id
                    }
                },
                timeout=10
            )
            
            print(f"MCP response: {response.status_code}")
            
        except Exception as e:
            print(f"Error processing {key}: {str(e)}")
            continue
    
    return {'statusCode': 200, 'body': json.dumps('Processed')}
"""),
            environment={
                "MCP_URL": ""  # Update this after deployment with http://EC2_IP:8080
            },
            vpc=vpc,
            allow_public_subnet=True,
            timeout=Duration.seconds(30)
        )
        
        documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(s3_processor)
        )

        # ===================================================================
        # 12. SECURITY GROUPS
        # ===================================================================
        instance_sg = asg.connections.security_groups[0]
        
        # Allow public access to all service ports
        for port in [80, 8080, 8000, 6333, 6379]:
            instance_sg.add_ingress_rule(
                ec2.Peer.any_ipv4(),
                ec2.Port.tcp(port),
                f"Public Access Port {port}"
            )
        
        # Allow EFS access from EC2 instances
        file_system.connections.allow_default_port_from(instance_sg)

        # ===================================================================
        # 13. OUTPUTS
        # ===================================================================
        CfnOutput(self, "EC2InstanceInfo",
            value="Use AWS Console or CLI to get EC2 public IP: aws ec2 describe-instances --filters 'Name=tag:aws:autoscaling:groupName,Values=*DefaultCapacity*' --query 'Reservations[0].Instances[0].PublicIpAddress'",
            description="Command to get EC2 Public IP"
        )
        
        CfnOutput(self, "ServiceEndpoints",
            value="After deployment, access services at: WebUI=http://EC2_IP:8080, Qdrant=http://EC2_IP:6333, MCP=http://EC2_IP:8080, Tenant=http://EC2_IP:8000",
            description="Service Access URLs (replace EC2_IP with actual IP)"
        )
        
        CfnOutput(self, "PostDeploymentSteps",
            value="1. Get EC2 IP using command above. 2. Update Cognito callback URL to http://EC2_IP:8080/oauth/callback. 3. Update Lambda MCP_URL to http://EC2_IP:8080",
            description="Required manual steps after deployment"
        )
        
        CfnOutput(self, "S3BucketName",
            value=documents_bucket.bucket_name,
            description="Documents S3 Bucket"
        )
        
        CfnOutput(self, "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )
        
        CfnOutput(self, "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID"
        )
        
        CfnOutput(self, "AutoScalingGroupName",
            value=asg.auto_scaling_group_name,
            description="Auto Scaling Group Name"
        )
        
        CfnOutput(self, "CostSavings",
            value="QA optimized: No ALB ($16-20/mo saved), Single AZ, t3.medium, Total memory: 2944MB",
            description="Cost optimizations applied"
        )