#!/usr/bin/env node
/**
 * Direct Coolify API Configuration Script
 * Bypasses MCP wrapper limitations to set base_directory and other fields
 */

const COOLIFY_BASE_URL = 'https://panel.laviefatigue.com';
const COOLIFY_TOKEN = '6|bAgRcMJ17aZpB4jpxMKiUzFcGkw7TqB2cP4QDdJp3e463911';

// Application UUIDs
const BACKEND_UUID = 'jc0o8cwok4ocgk8c0sw440kk';
const FRONTEND_UUID = 'vwg8400ww4s844wsgg4s0ogc';

async function coolifyRequest(method, path, body = null) {
  const url = `${COOLIFY_BASE_URL}/api/v1${path}`;
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Authorization': `Bearer ${COOLIFY_TOKEN}`,
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  console.log(`\n${method} ${path}`);
  if (body) console.log('Body:', JSON.stringify(body, null, 2));

  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    console.error(`Error ${response.status}:`, data);
    return { error: true, status: response.status, data };
  }

  console.log('Success:', response.status);
  return { error: false, data };
}

async function configureBackend() {
  console.log('\n=== Configuring Backend (charm-api) ===');

  // Update application with base_directory
  const result = await coolifyRequest('PATCH', `/applications/${BACKEND_UUID}`, {
    base_directory: '/api',
    dockerfile_location: '/Dockerfile',
    ports_exposes: '8000',
  });

  if (result.error) {
    console.log('Failed to update backend configuration');
    return false;
  }

  console.log('Backend configuration updated successfully');
  return true;
}

async function configureFrontend(apiUrl) {
  console.log('\n=== Configuring Frontend (charm-frontend) ===');

  // Update application with base_directory
  const result = await coolifyRequest('PATCH', `/applications/${FRONTEND_UUID}`, {
    base_directory: '/charm-email-os',
    dockerfile_location: '/Dockerfile',
    ports_exposes: '3000',
  });

  if (result.error) {
    console.log('Failed to update frontend configuration');
    return false;
  }

  console.log('Frontend configuration updated successfully');
  return true;
}

async function createEnvVars(appUuid, vars) {
  console.log(`\nCreating ${vars.length} env vars for ${appUuid}...`);

  // Use bulk endpoint
  const result = await coolifyRequest('PATCH', `/applications/${appUuid}/envs/bulk`, {
    data: vars
  });

  if (result.error) {
    console.log('Failed to create environment variables');
    return false;
  }

  console.log('Environment variables created successfully');
  return true;
}

async function getApplication(uuid) {
  const result = await coolifyRequest('GET', `/applications/${uuid}`);
  return result.error ? null : result.data;
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'configure';

  switch (command) {
    case 'configure':
      console.log('=== Coolify Configuration Script ===');

      // Configure backend
      await configureBackend();

      // Configure frontend
      await configureFrontend();

      console.log('\n=== Configuration Complete ===');
      console.log('\nNext steps:');
      console.log('1. Add environment variables via Coolify UI or this script');
      console.log('2. Set up GitHub App in Coolify for private repo access');
      console.log('3. Deploy the applications');
      break;

    case 'status':
      console.log('=== Application Status ===');
      const backend = await getApplication(BACKEND_UUID);
      const frontend = await getApplication(FRONTEND_UUID);

      console.log('\nBackend (charm-api):');
      console.log('  Status:', backend?.status || 'unknown');
      console.log('  Base Directory:', backend?.base_directory || 'not set');
      console.log('  Dockerfile:', backend?.dockerfile_location || 'not set');

      console.log('\nFrontend (charm-frontend):');
      console.log('  Status:', frontend?.status || 'unknown');
      console.log('  Base Directory:', frontend?.base_directory || 'not set');
      console.log('  Dockerfile:', frontend?.dockerfile_location || 'not set');
      break;

    case 'backend-env':
      const postgresPassword = args[1];
      if (!postgresPassword) {
        console.error('Usage: node configure-coolify.mjs backend-env <postgres_password>');
        process.exit(1);
      }

      await createEnvVars(BACKEND_UUID, [
        { key: 'POSTGRES_HOST', value: '31.97.142.123' },
        { key: 'POSTGRES_PORT', value: '5432' },
        { key: 'POSTGRES_DB', value: 'postgres' },
        { key: 'POSTGRES_USER', value: 'postgres' },
        { key: 'POSTGRES_PASSWORD', value: postgresPassword },
        { key: 'POSTGRES_SCHEMA', value: 'public' },
        { key: 'DEBUG', value: 'false' },
      ]);
      break;

    case 'frontend-env':
      const apiUrl = args[1];
      if (!apiUrl) {
        console.error('Usage: node configure-coolify.mjs frontend-env <api_url>');
        process.exit(1);
      }

      await createEnvVars(FRONTEND_UUID, [
        { key: 'NEXT_PUBLIC_API_URL', value: apiUrl, is_build_time: true },
      ]);
      break;

    default:
      console.log('Usage: node configure-coolify.mjs [configure|status|backend-env|frontend-env]');
  }
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
