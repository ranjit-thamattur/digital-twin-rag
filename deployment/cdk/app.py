#!/usr/bin/env python3
import os

import aws_cdk as cdk

from clonemind.clonemind_stack import CloneMindStack


app = cdk.App()
CloneMindStack(app, "CloneMindStack",
    # Specify your AWS Account ID and Region here
    env=cdk.Environment(
        account='YOUR_AWS_ACCOUNT_ID', 
        region='us-east-1'
    ),
)

app.synth()
