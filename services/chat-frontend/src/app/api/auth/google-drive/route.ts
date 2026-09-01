import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const clientId = process.env.GOOGLE_CLIENT_ID || 'PLACEHOLDER_CLIENT_ID';
  
  // Use the explicit APP URL env var. This prevents ALB from stripping the origin header
  // and generating a wrong redirect URI like http://localhost:3000
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://ai.peakpa.com';
  const redirectUri = `${appUrl}/api/auth/google-drive/callback`;

  // drive.file: can read/write files the app creates or opens (safer than drive.readonly for our use case)
  // We need write access to create the "Digital Brain Sync" folder if it doesn't exist
  const scope = 'https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/drive.readonly';

  const googleAuthUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  googleAuthUrl.searchParams.append('client_id', clientId);
  googleAuthUrl.searchParams.append('redirect_uri', redirectUri);
  googleAuthUrl.searchParams.append('response_type', 'code');
  googleAuthUrl.searchParams.append('scope', scope);
  googleAuthUrl.searchParams.append('access_type', 'offline');
  googleAuthUrl.searchParams.append('prompt', 'consent');

  return NextResponse.redirect(googleAuthUrl.toString());
}
