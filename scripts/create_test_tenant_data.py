#!/usr/bin/env python3
"""
Script to create a test tenant 'Thinkering' and seed realistic business test data
covering all 4 Digital Brain action scenarios:
1. Plan my day
2. Check a customer
3. Find risks
4. Explore scenarios
"""

import os
import sys
import json
import boto3
from datetime import datetime

# AWS Region & DynamoDB
REGION = os.getenv("AWS_REGION", "us-east-1")
TENANT_TABLE = os.getenv("TENANT_TABLE", "clonemind-tenants")
DOCUMENTS_BUCKET = os.getenv("DOCUMENTS_BUCKET_NAME", "clonemind-docs")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

TENANT_ID = "tenant-testsomething"
COMPANY_NAME = "Test Something Inc"
ADMIN_EMAIL = "admin@testsomething.com"

# 1. Seed Tenant metadata into DynamoDB
def create_test_tenant():
    print(f"1. Creating tenant '{TENANT_ID}' ({COMPANY_NAME}) in DynamoDB table '{TENANT_TABLE}'...")
    table = dynamodb.Table(TENANT_TABLE)
    item = {
        "tenantId": TENANT_ID,
        "tenantName": "Thinkering",
        "companyName": COMPANY_NAME,
        "industry": "AI & Software Technology",
        "adminEmail": ADMIN_EMAIL,
        "isActive": True,
        "plan": "premium",
        "allowedPersonas": ["ceo", "manager", "analyst", "hr_manager"],
        "defaultPersona": "ceo",
        "createdAt": datetime.now().isoformat(),
    }
    table.put_item(Item=item)
    print("✅ Tenant registered in DynamoDB!")

# 2. Sample Business Test Documents
DOCUMENTS = {
    "Plan_My_Day_Schedule.txt": """
DAILY EXECUTIVE SCHEDULE & PRIORITY TASKS - 12 AUG 2025
======================================================
User: Admin (CEO, Test Something Inc)

PRIORITY TASKS FOR TODAY:
1. 10:00 AM - Executive Leadership Sync on Q3 Growth Strategy and product roadmap.
2. 01:30 PM - Client Call with Acme Corp regarding enterprise contract renewal ($120,000/yr).
3. 03:30 PM - Review 5 overdue customer invoices with Finance lead (Total overdue: ₹12,40,000).
4. 05:00 PM - Finalize sales expansion proposal for hiring 1 Senior Sales Representative.

PENDING ACTION ITEMS & FOLLOW-UPS:
- Send revised digital twin demo proposal to GlobalTech Systems.
- Sign GST quarterly return filing (Due in 3 days).
- Approve travel expense budget for regional sales team.
""",

    "Customer_History_AcmeCorp.txt": """
CUSTOMER ACCOUNT HISTORY - ACME CORP
===================================
Account ID: ACME-8842
Company Name: Acme Corporation
Industry: Industrial Automation & Robotics
Contract Tier: Enterprise Plan
Account Executive: Alex Rivera

CONTRACT & QUOTATION HISTORY:
- 2023 Initial Deal: $250,000 annual recurring contract for RAG knowledge platform.
- 2025 Active Renewal Quote #Q-2026-941: $120,000/year for Digital Brain expansion.
- Lifetime Value (LTV): $450,000.

ACTIVE PROMISES & SLA:
- Promised 99.9% uptime SLA with 1-hour critical response guarantee.
- Promised dedicated AI Solutions Engineer (Alex Rivera) assigned to team.
- Promised custom Qdrant vector index integration by Q4 2025.

OPEN TICKETS & FEEDBACK:
- Ticket #TK-9021: Requesting SSO integration for 150 employees (Status: In Progress).
""",

    "Risk_Register_Overdue_Payments.txt": """
FINANCIAL RISK REGISTER & OVERDUE PAYMENTS
=========================================
Company: Test Something Inc
As of: 12 Aug 2025
Total Overdue Outstanding: ₹12,40,000 across 5 invoices.

OVERDUE INVOICES BREAKDOWN:
1. Invoice #INV-1092 | Acme Corp | Amount: ₹4,50,000 | Overdue: 65 Days | Risk Level: HIGH (Amygdala Threat Triggered)
2. Invoice #INV-1088 | Stark Industries | Amount: ₹3,20,000 | Overdue: 45 Days | Risk Level: MEDIUM
3. Invoice #INV-1075 | Apex Global | Amount: ₹2,10,000 | Overdue: 30 Days | Risk Level: MEDIUM
4. Invoice #INV-1064 | Cyberdyne Systems | Amount: ₹1,60,000 | Overdue: 25 Days | Risk Level: LOW
5. Invoice #INV-1051 | Wayne Tech | Amount: ₹1,00,000 | Overdue: 15 Days | Risk Level: LOW

ACTION ITEMS REQUIRED:
- Issue formal payment reminder letter for Invoice #INV-1092 (Acme Corp).
- Escalate 60+ days overdue account to finance compliance lead.
- GST filing due in 3 days (15 Aug 2025). Prepare returns to avoid penalty.
""",

    "Scenario_Salesperson_Hiring_Projection.txt": """
BUSINESS SCENARIO ANALYSIS: HIRING 1 SENIOR SALES REPRESENTATIVE
==============================================================
Company: Test Something Inc
Date: Aug 2025

CURRENT TEAM DATA & METRICS:
- Current Salespeople: 10
- Average Revenue per Salesperson: ₹40,00,000 / year
- Annual Cost of New Salesperson: ₹12,00,000 / year
- Current Conversion Rate: 20%

HIRING SCENARIO MODELING (1 NEW SALESPERSON):
- Potential Additional Revenue (at current team average): ₹40,00,000
- Additional Annual Cost: ₹12,00,000
- Potential Net Contribution: ₹28,00,000

THREE CRITICAL FACTORS TO CONSIDER BEFORE HIRING:
1. Capacity: Are existing salespeople already fully utilized?
2. Pipeline: Is there enough qualified pipeline for another salesperson?
3. Ramp-up: How long will the new salesperson take to reach ₹40L productivity?

DECISION QUESTIONS & MULTI-HIRE MODELING:
- Main Question: Do we have enough demand, or are we simply adding capacity?
- Alternative Question: "How many salespeople can I profitably support?"
- Modeling Options: 0 hires → 1 hire → 2 hires → 3 hires to show exact profitable growth thresholds.
"""
}

# 3. Upload Test Documents to S3 & Local Storage
def upload_test_documents():
    print(f"\n2. Uploading 4 test documents for '{TENANT_ID}' (persona: ceo) to S3 bucket '{DOCUMENTS_BUCKET}'...")
    os.makedirs("demo-docs/TestSomething", exist_ok=True)
    
    for filename, content in DOCUMENTS.items():
        # Save locally
        filepath = os.path.join("demo-docs/TestSomething", filename)
        with open(filepath, "w") as f:
            f.write(content.strip())
        
        # Upload to S3 under tenant prefix: {tenant_id}/ceo/{filename}
        s3_key = f"{TENANT_ID}/ceo/{filename}"
        try:
            s3.put_object(
                Bucket=DOCUMENTS_BUCKET,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType="text/plain"
            )
            print(f"  ✅ Uploaded S3: s3://{DOCUMENTS_BUCKET}/{s3_key}")
        except Exception as e:
            print(f"  ⚠️ S3 upload notice (Saved locally at {filepath}): {str(e)}")

if __name__ == "__main__":
    print("==================================================")
    print("🚀 SEEDING TEST TENANT 'TEST SOMETHING' AND DATA")
    print("==================================================")
    create_test_tenant()
    upload_test_documents()
    print("\n🎉 TEST TENANT SETUP COMPLETE!")
    print(f"  Tenant ID: {TENANT_ID}")
    print(f"  Company: {COMPANY_NAME}")
    print(f"  User: Admin ({ADMIN_EMAIL})")
    print("==================================================")

