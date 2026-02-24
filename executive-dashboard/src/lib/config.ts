// Configuration for Charm Executive Dashboard
// Hardcoded to Charm client for internal use

export const config = {
  // Charm client ID (from database)
  clientId: '4bd07dc0-059a-448b-b6f4-3275d0c104a9',

  // API URL - use Docker internal network when in container
  // Priority: API_URL (runtime) > NEXT_PUBLIC_API_URL (build) > default (Docker network)
  apiUrl: process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://charm-api:8000',

  // Refresh interval (5 minutes)
  refreshInterval: 300000,
} as const;
