import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const cognitoLogoutUrl = 'https://clonemind-543187302175.auth.us-east-1.amazoncognito.com/logout?client_id=70josbv1q9rjfhgji773k8p3gk&logout_uri=https://ai.peakpa.com';

  const response = NextResponse.redirect(cognitoLogoutUrl);

  // AWS ALB uses these HttpOnly cookies to track authenticated sessions.
  // We MUST explicitly expire them on the server side to fully log the user out of the ALB.
  response.cookies.set('AWSELBAuthSessionCookie-0', '', { expires: new Date(0), path: '/' });
  response.cookies.set('AWSELBAuthSessionCookie-1', '', { expires: new Date(0), path: '/' });

  // Also clear Next.js auth token if any
  response.cookies.set('auth-token', '', { expires: new Date(0), path: '/' });

  return response;
}
