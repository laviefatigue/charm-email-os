import { headers } from 'next/headers';
import { NextResponse } from 'next/server';

/**
 * GET /api/auth/user
 *
 * Returns the current authenticated user from Cloudflare Access headers.
 * In production, Cloudflare Access injects CF-Access-Authenticated-User-Email
 * after successful Google OAuth authentication.
 *
 * For local development without Cloudflare, returns a mock user.
 */
export async function GET() {
  const headersList = await headers();

  // Cloudflare Access injects this header for authenticated users
  let userEmail = headersList.get('cf-access-authenticated-user-email');

  // For local development ONLY, allow dev override header or use mock
  // SECURITY: Never allow x-dev-user-email in production
  if (!userEmail && process.env.NODE_ENV === 'development') {
    const devEmail = headersList.get('x-dev-user-email');
    if (devEmail) {
      userEmail = devEmail;
    } else {
      // Mock user for local development
      userEmail = 'dev@hirecharm.com';
    }
  }

  if (!userEmail) {
    // Not authenticated (shouldn't happen in production behind Cloudflare Access)
    return NextResponse.json({
      email: null,
      displayName: null,
      initials: null,
      authenticated: false
    });
  }

  // Derive display name from email (e.g., john.doe@hirecharm.com -> John Doe)
  const namePart = userEmail.split('@')[0];
  const displayName = namePart
    .split(/[._-]/)  // Split on common separators
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');

  // Get initials for avatar (up to 2 characters)
  const words = displayName.split(' ').filter(w => w.length > 0);
  const initials = words.length >= 2
    ? `${words[0][0]}${words[1][0]}`.toUpperCase()
    : displayName.slice(0, 2).toUpperCase();

  return NextResponse.json({
    email: userEmail,
    displayName,
    initials,
    authenticated: true,
  });
}
