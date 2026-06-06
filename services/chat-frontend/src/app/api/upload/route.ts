import { NextResponse } from 'next/server';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';

// Initialize S3 Client (it will automatically use the ECS Task Role credentials)
const s3Client = new S3Client({ region: process.env.AWS_REGION || 'us-east-1' });

// Parse the ALB Cognito JWT to get the user's email
function extractEmailFromOidc(oidcData: string | null): string | null {
  if (!oidcData) return null;
  try {
    const payload = oidcData.split('.')[1];
    const decoded = Buffer.from(payload, 'base64').toString('utf-8');
    const json = JSON.parse(decoded);
    return json.email || null;
  } catch (e) {
    console.error('Failed to parse OIDC token:', e);
    return null;
  }
}

export async function POST(request: Request) {
  try {
    // 1. Get Identity from AWS ALB Cognito Headers
    const headers = request.headers;
    let email = extractEmailFromOidc(headers.get('x-amzn-oidc-data'));
    
    // Fallbacks for local testing
    if (!email) {
      email = headers.get('x-user-email') || 'ceo@11xcompany.com';
    }

    // 2. Resolve Tenant and Persona from Email
    let tenantId = 'default';
    let personaId = 'global';

    if (email && email.includes('@')) {
      const parts = email.split('@');
      const domain = parts[1].toLowerCase();
      
      if (domain.includes('11x')) {
        tenantId = 'tenant-11x';
        personaId = parts[0] === 'hr' ? 'hr_manager' : parts[0];
      } else {
        const cleanDomain = domain.split('.')[0];
        tenantId = `tenant-${cleanDomain}`;
        personaId = parts[0] === 'hr' ? 'hr_manager' : parts[0];
      }
    }

    console.log(`[Upload API] Authenticated User: ${email} -> Tenant: ${tenantId} | Persona: ${personaId}`);

    // 3. Process the file and parameters
    const formData = await request.formData();
    const file = formData.get('file') as File | null;
    const isCommon = formData.get('isCommon') === 'true';

    if (!file) {
      return NextResponse.json({ error: 'No file provided.' }, { status: 400 });
    }

    // Override personaId if uploading to common
    if (isCommon) {
      personaId = 'common';
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);

    // 4. Upload to S3
    const bucketName = process.env.DOCUMENTS_BUCKET_NAME;
    if (!bucketName) {
      console.error('DOCUMENTS_BUCKET_NAME is not configured.');
      return NextResponse.json({ error: 'Server configuration error.' }, { status: 500 });
    }

    // The S3 path required by the S3ToMcpProcessor Lambda is: tenant/persona/filename
    const s3Key = `${tenantId}/${personaId}/${file.name}`;
    
    console.log(`[Upload API] Uploading ${file.name} to s3://${bucketName}/${s3Key}`);

    const command = new PutObjectCommand({
      Bucket: bucketName,
      Key: s3Key,
      Body: buffer,
      ContentType: file.type || 'application/octet-stream',
      Metadata: {
        'uploaded-by': email
      }
    });

    await s3Client.send(command);

    console.log(`[Upload API] Upload successful.`);

    return NextResponse.json({ 
      success: true, 
      message: 'File uploaded successfully. Processing...',
      s3Key 
    });

  } catch (error) {
    console.error('Upload API Error:', error);
    return NextResponse.json({ error: 'Failed to upload file.' }, { status: 500 });
  }
}
