#!/usr/bin/env python3
import os

import aws_cdk as cdk

from clonemind.clonemind_stack import CloneMindStack


app = cdk.App()
CloneMindStack(app, "CloneMindStackV2",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    ),
)

app.synth()
