import os
import base64
import pathlib
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
    aws_autoscaling as autoscaling,
    aws_s3_notifications as s3n,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_certificatemanager as acm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_actions as elbv2_actions,
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
            max_azs=2, # Internet-facing ALB requires at least 2 AZs
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
            min_capacity=1,
            max_capacity=1,
            desired_capacity=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            associate_public_ip_address=True,
            block_devices=[
                autoscaling.BlockDevice(
                    device_name="/dev/xvda",
                    volume=autoscaling.BlockDeviceVolume.ebs(100,
                        volume_type=autoscaling.EbsDeviceVolumeType.GP3
                    )
                )
            ]
        )
        
        asg.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonEC2ContainerServiceforEC2Role"
            )
        )
        
        # Add Bedrock and Marketplace permissions to Instance Role
        asg.role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:GetInferenceProfile",
                    "aws-marketplace:ViewSubscriptions",
                    "aws-marketplace:Subscribe"
                ],
                resources=["*"]
            )
        )
        asg.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )

        # ===================================================================
        # 2b. ELASTIC IP - Static IP for EC2 (so Lambda MCP_URL never changes)
        # ===================================================================
        eip = ec2.CfnEIP(self, "CloneMindEIP", domain="vpc")

        # Auto-associate EIP on instance startup via user data.
        # Retry loop handles the race condition where the IAM instance profile
        # is not fully propagated when user-data first runs at boot.
        asg.add_user_data(
            "INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)",
            "REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)",
            "echo 'Associating Elastic IP...' | logger -t eip-associate",
            "for i in 1 2 3 4 5; do",
            f"  aws ec2 associate-address --instance-id $INSTANCE_ID --allocation-id {eip.attr_allocation_id} --region $REGION --allow-reassociation && echo 'EIP associated OK' | logger -t eip-associate && break",
            "  echo \"EIP attempt $i failed, retrying in 10s...\" | logger -t eip-associate",
            "  sleep 10",
            "done",
            # Add hourly Docker cleanup to prevent disk issues
            "echo '0 * * * * root /usr/bin/docker image prune -af >> /var/log/docker-prune.log 2>&1' > /etc/cron.d/docker-cleanup"
        )

        # Grant permission to associate the EIP
        asg.role.add_to_policy(
            iam.PolicyStatement(
                actions=["ec2:AssociateAddress"],
                resources=["*"]
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
        
        user_pool_domain = user_pool.add_domain("CognitoDomain", 
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
                    "http://localhost:8080/oauth/oidc/callback",
                    "https://ai.peakpa.com/oauth/callback",
                    "https://ai.peakpa.com/oauth/oidc/callback",
                    "https://ai.peakpa.com/oauth2/idpresponse"
                ],
                logout_urls=[
                    "http://localhost:8080",
                    "https://ai.peakpa.com"
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
        # 3b. COGNITO HOSTED UI BRANDING — Peak AI
        # ===================================================================
        # NOTE: Temporarily commented out due to strict/buggy Cognito CSS validator 
        # in some regions. Apply branding manually in AWS Console for better feedback.
        #
        # _css_path = pathlib.Path(__file__).parent / "cognito_ui.css"
        # _css_content = _css_path.read_text()
        #
        # cognito.CfnUserPoolUICustomizationAttachment(
        #     self, "PeakUICustomization",
        #     user_pool_id=user_pool.user_pool_id,
        #     client_id="ALL",       # Apply branding to ALL app clients
        #     css=_css_content,
        # )

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
        
        history_table = dynamodb.Table(self, "ChatHistory",
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,
            table_name=f"clonemind-chat-history-{self.account}"
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
        qdrant_ap = create_access_point("QdrantAP", "/qdrant")

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

        # Mount EFS so Qdrant vector data persists across instance replacements
        qdrant_task.add_volume(
            name="QdrantStorage",
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
            memory_limit_mib=768,
            cpu=256,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Qdrant")
        )
        qdrant_container.add_port_mappings(
            ecs.PortMapping(container_port=6333, host_port=6333),
            ecs.PortMapping(container_port=6334, host_port=6334)
        )
        qdrant_container.add_mount_points(
            ecs.MountPoint(
                container_path="/qdrant/storage",
                source_volume="QdrantStorage",
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
            "DISABLE_SEMANTIC_CACHE": "false",
            "EMBEDDING_PROVIDER": "titan",
            "LLM_PROVIDER": "bedrock",
            # ✅ Amazon Nova Pro (Active & bypasses Marketplace billing blocks)
            "PRIMARY_MODEL": "amazon.nova-pro-v1:0",
            "REWRITE_MODEL": "mistral.ministral-3-14b-instruct",
            "RERANK_MODEL": "cohere.rerank-v3-5:0"
        }
        
        mcp_task = ecs.Ec2TaskDefinition(self, "McpTask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        mcp_container = mcp_task.add_container("McpContainer",
            image=ecs.ContainerImage.from_asset("../../services/mcp-server"),
            memory_limit_mib=512,  # Shrunk from 2048 since we removed PyTorch
            cpu=512,               # Increased for better performance
            environment=mcp_env,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Mcp")
        )
        mcp_container.add_port_mappings(
            ecs.PortMapping(container_port=3000, host_port=3000)
        )
        
        tenant_table.grant_read_write_data(mcp_task.task_role)
        documents_bucket.grant_read(mcp_task.task_role)
        
        # Grant Bedrock access to both Task and Execution roles
        for role in [mcp_task.task_role, mcp_task.execution_role]:
            if role:
                role.add_to_policy(
                    iam.PolicyStatement(
                        actions=[
                            "bedrock:InvokeModel",
                            "bedrock:InvokeModelWithResponseStream",
                            "bedrock:GetInferenceProfile",
                            "aws-marketplace:ViewSubscriptions",
                            "aws-marketplace:Subscribe"
                        ],
                        resources=["*"]
                    )
                )
        
        mcp_service = ecs.Ec2Service(self, "McpService", 
            cluster=cluster, 
            task_definition=mcp_task,
            desired_count=1,
            min_healthy_percent=0,
            service_name="mcp-server",
            enable_execute_command=True
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
            service_name="tenant-service",
            enable_execute_command=True
        )

        # ===================================================================
        # 10. WEBUI SERVICE
        # ===================================================================
        # ===================================================================
        frontend_task = ecs.Ec2TaskDefinition(self, "FrontendTask", 
            network_mode=ecs.NetworkMode.BRIDGE
        )
        
        frontend_container = frontend_task.add_container("FrontendContainer",
            image=ecs.ContainerImage.from_asset("../../services/chat-frontend"),
            memory_limit_mib=512,
            cpu=256,
            environment={
                "PORT": "3000",
                "NEXT_PUBLIC_APP_URL": "https://ai.peakpa.com",
                # Google OAuth credentials for Google Drive integration
                # Set these via: aws ssm put-parameter --name /digital-brain/GOOGLE_CLIENT_ID --value "your-id" --type SecureString
                #                aws ssm put-parameter --name /digital-brain/GOOGLE_CLIENT_SECRET --value "your-secret" --type SecureString
            },
            secrets={
                "GOOGLE_CLIENT_ID": ecs.Secret.from_ssm_parameter(
                    ssm.StringParameter.from_secure_string_parameter_attributes(
                        frontend_task, "GoogleClientId",
                        parameter_name="/digital-brain/GOOGLE_CLIENT_ID",
                        version=1
                    )
                ),
                "GOOGLE_CLIENT_SECRET": ecs.Secret.from_ssm_parameter(
                    ssm.StringParameter.from_secure_string_parameter_attributes(
                        frontend_task, "GoogleClientSecret",
                        parameter_name="/digital-brain/GOOGLE_CLIENT_SECRET",
                        version=1
                    )
                ),
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Frontend")
        )
        
        # Grant DynamoDB permissions to the frontend so it can save OAuth tokens
        tenant_table.grant_read_write_data(frontend_task.task_role)
        
        frontend_container.add_port_mappings(
            ecs.PortMapping(container_port=3000, host_port=3001)
        )
        frontend_task.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["polly:SynthesizeSpeech"],
                resources=["*"]
            )
        )
        
        frontend_service = ecs.Ec2Service(self, "FrontendService", 
            cluster=cluster, 
            task_definition=frontend_task,
            desired_count=1,
            min_healthy_percent=0,
            service_name="chat-frontend",
            enable_execute_command=True
        )

        # ===================================================================
        # 11. PRODUCTION ACCESS: ALB + HTTPS
        #     Domain: ai.peakpa.com  |  DNS managed externally (Hostinger/GoDaddy)
        #     Certificate: ACM (us-east-1), validated via CNAME in DNS provider
        # ===================================================================
        
        # 1. Import pre-existing ACM Certificate by ARN
        #    Certificate covers ai.peakpa.com, validated in us-east-1.
        cert = acm.Certificate.from_certificate_arn(
            self, "SiteCert",
            certificate_arn="arn:aws:acm:us-east-1:543187302175:certificate/f79ec0e6-6486-4d3e-b37f-e3e72dedcc94"
        )
        
        # 2. Application Load Balancer
        lb = elbv2.ApplicationLoadBalancer(self, "CloneMindALB",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )
        
        # Inject dynamic environment variables to Frontend container
        frontend_container.add_environment("MCP_SERVER_URL", f"http://{lb.load_balancer_dns_name}:3000")
        frontend_container.add_environment("DOCUMENTS_BUCKET_NAME", documents_bucket.bucket_name)
        frontend_container.add_environment("CHAT_HISTORY_TABLE_NAME", history_table.table_name)
        
        # Grant Frontend access to upload files and save chat history
        documents_bucket.grant_read_write(frontend_task.task_role)
        history_table.grant_read_write_data(frontend_task.task_role)
        
        # 3. HTTP Listener -> Redirect to HTTPS
        lb.add_listener("HttpListener",
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True
            )
        )
        
        # 4. HTTPS Listener with imported certificate
        https_listener = lb.add_listener("HttpsListener",
            port=443,
            certificates=[cert],
            open=True
        )
        
        # Create the Target Group first so it can be reused
        frontend_target = https_listener.add_targets("FrontendTarget",
            port=3001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[frontend_service],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(60)
            )
        )

        # 5. Default Action: Cognito Authentication (Protects /*)
        https_listener.add_action("CognitoAuthAction",
            action=elbv2_actions.AuthenticateCognitoAction(
                user_pool=user_pool,
                user_pool_client=webui_client,
                user_pool_domain=user_pool_domain,
                next=elbv2.ListenerAction.forward([frontend_target])
            )
        )

        # 6. Bypass Action: Allow unauthenticated access to Login Page & Assets
        https_listener.add_action("BypassAuthAction",
            priority=10,
            conditions=[
                elbv2.ListenerCondition.path_patterns(["/", "/api/auth/verify*", "/_next/*", "/peak_logo*", "/digital_brain_bg*"])
            ],
            action=elbv2.ListenerAction.forward([frontend_target])
        )

        # 7. Webhook Bypass Action: Allow unauthenticated access to Webhooks
        https_listener.add_action("WebhookBypassAction",
            priority=11,
            conditions=[
                elbv2.ListenerCondition.path_patterns(["/api/webhooks/google-drive*"])
            ],
            action=elbv2.ListenerAction.forward([frontend_target])
        )
        
        # 6. HTTP Listener for Ingestion (Port 3000)
        # Lambda calls this to forward S3 events to MCP
        mcp_listener = lb.add_listener("McpListener",
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            open=True
        )
        mcp_listener.add_targets("McpTarget",
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[mcp_service],
            health_check=elbv2.HealthCheck(
                path="/", # FastMCP default root
                interval=Duration.seconds(60)
            )
        )

        # ===================================================================
        # 12. S3 PROCESSOR LAMBDA
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
        key = "unknown"
        try:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            parts = key.split('/')
            
            if len(parts) < 3:
                print(f"⚠️ Skipping {key}: path does not follow 'tenant/persona/file' structure")
                continue
            
            tenant_id = parts[0]
            persona_id = parts[1]
            filename = parts[-1]
            
            print(f"🚀 Processing: s3://{bucket}/{key} | Tenant: {tenant_id} | Persona: {persona_id}")
            
            payload = {
                "s3_bucket": bucket,
                "s3_key": key,
                "tenantId": tenant_id,
                "metadata": {
                    "filename": filename,
                    "s3_key": key,
                    "personaId": persona_id,
                    "ingested_at": int(time.time()),
                    "original_event_id": record.get('eventID')
                }
            }
            
            print(f"📡 Forwarding to MCP: {mcp_url}/call/ingest_knowledge")
            # print(f"DEBUG Payload: {json.dumps(payload)}")
            
            req = urllib.request.Request(
                f"{mcp_url}/call/ingest_knowledge",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    status = response.getcode()
                    resp_body = response.read().decode('utf-8')
                    print(f"✅ Success [{status}]: {key} | Response: {resp_body}")
            except urllib.error.HTTPError as he:
                print(f"❌ MCP HTTP Error {he.code} for {key}: {he.read().decode('utf-8')}")
            except Exception as req_err:
                print(f"❌ MCP Request failed for {key}: {str(req_err)}")
            
        except Exception as e:
            print(f"💥 Unexpected error processing {key}: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
    
    return {'statusCode': 200, 'body': 'Processed all records'}
"""),
            environment={
                # Uses the static Elastic IP - will never change even if EC2 is replaced
                # Uses the Load Balancer DNS - stable and AWS-native
                "MCP_URL": f"http://{lb.load_balancer_dns_name}:3000"
            },
            timeout=Duration.seconds(180),
            memory_size=512
        )
        
        documents_bucket.grant_read(s3_processor)
        
        documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(s3_processor)
        )

        
        # Note: No Route53 Alias Record created.
        # DNS is managed in Hostinger:
        # Add a CNAME record:  ai  ->  <LoadBalancerDNS output>

        # ===================================================================
        # 13. SECURITY GROUPS

        # ===================================================================
        instance_sg = asg.connections.security_groups[0]
        
        # Allow traffic only from ALB to instances
        instance_sg.connections.allow_from(
            lb, 
            ec2.Port.tcp(8080), 
            "Allow WebUI Access from ALB"
        )
        # Allow Lambda (outside VPC) to reach MCP server
        instance_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(3000),
            "Allow MCP Server access from Lambda"
        )
        # Allow Direct Public access to Qdrant Dashboard
        instance_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(6333),
            "Allow Qdrant Dashboard access"
        )
        # Allow admin access to Tenant Service API
        instance_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(8000),
            "Allow Tenant Service admin API access"
        )
        # If other services need to be accessed via ALB, add them here.
        # But initially we are only exposing WebUI at root.
        
        file_system.connections.allow_default_port_from(instance_sg)

        # ===================================================================
        # 13. OUTPUTS
        # ===================================================================
        CfnOutput(self, "ProductionURL",
            value="https://ai.peakpa.com",
            description="Production URL (after updating Hostinger CNAME)"
        )
        
        CfnOutput(self, "LoadBalancerDNS",
            value=lb.load_balancer_dns_name,
            description="ALB DNS Name"
        )
        
        CfnOutput(self, "PostDeploymentSteps",
            value="1. Verify https://ai.peakpa.com works. 2. Update Auth Callbacks if needed.",
            description="Manual steps after deployment"
        )
        
        CfnOutput(self, "S3BucketName", value=documents_bucket.bucket_name)
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "WebUIClientId", value=webui_client.user_pool_client_id)
        CfnOutput(self, "AdminClientId", value=admin_client.user_pool_client_id)
        CfnOutput(self, "LambdaFunctionName", value=s3_processor.function_name)
        CfnOutput(self, "ElasticIP",
            value=eip.attr_public_ip,
            description="Static Elastic IP for EC2 instance (used in Lambda MCP_URL)"
        )
        
        # New output for OpenAI setup
        CfnOutput(self, "OpenAiProvider",
            value="Active (via Environment Variable)",
            description="Status of OpenAI Provider"
        )