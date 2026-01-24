# Digital Twin RAG - CDK Deployment

This directory contains the Python-based AWS Cloud Development Kit (CDK) project for deploying the Digital Twin RAG infrastructure to AWS.

## Prerequisites

- AWS CLI configured
- Node.js (for CDK CLI)
- Python 3.11+

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```

2. Activate virtual environment:
   - macOS/Linux: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

- `cdk ls`          list all stacks in the app
- `cdk synth`       emits the synthesized CloudFormation template
- `cdk deploy`      deploy this stack to your default AWS account/region
- `cdk diff`        compare deployed stack with current state
- `cdk destroy`     tear down the stack
