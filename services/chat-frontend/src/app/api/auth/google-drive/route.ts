import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  // Use environment variables (which the user will set later)
  const clientId = process.env.GOOGLE_CLIENT_ID || 'PLACEHOLDER_CLIENT_ID';
  // Use the origin from the request or a default for local development
  const origin = req.headers.get('origin') || 'http://localhost:3000';
  const redirectUri = `${origin}/api/auth/google-drive/callback`;

  // We need Read-Only drive access
  const scope = 'https://www.googleapis.com/auth/drive.readonly';

  // Construct the Google OAuth URL
  const googleAuthUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  googleAuthUrl.searchParams.append('client_id', clientId);
  googleAuthUrl.searchParams.append('redirect_uri', redirectUri);
  googleAuthUrl.searchParams.append('response_type', 'code');
  googleAuthUrl.searchParams.append('scope', scope);
  googleAuthUrl.searchParams.append('access_type', 'offline');
  googleAuthUrl.searchParams.append('prompt', 'consent'); // Force consent screen to always get refresh token

  // Redirect the user to Google
  return NextResponse.redirect(googleAuthUrl.toString());
}
