/**
 * Sender Name Generation Utility
 *
 * Generates sender names for Hypertide inbox provisioning.
 * Hypertide allows max 10 names per order, and names are reused across domains.
 *
 * Package name requirements:
 * - Starter: 6 Entra + 5 Google orders = needs 10 unique names
 * - Growth: 12 Entra + 10 Google orders = needs 10 unique names (same max)
 */

import type { OnboardingPersona, SenderName } from './types';

// Common first names for cold email (professional, neutral)
const FIRST_NAMES = [
  'Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey',
  'Riley', 'Cameron', 'Avery', 'Parker', 'Quinn',
  'Jamie', 'Drew', 'Blake', 'Reese', 'Skyler',
  'Sam', 'Chris', 'Pat', 'Robin', 'Dana',
];

// Common last names
const LAST_NAMES = [
  'Smith', 'Johnson', 'Williams', 'Brown', 'Davis',
  'Miller', 'Wilson', 'Moore', 'Taylor', 'Anderson',
  'Thomas', 'Jackson', 'White', 'Harris', 'Martin',
  'Thompson', 'Garcia', 'Martinez', 'Robinson', 'Clark',
];

/**
 * Generate email prefix from name (e.g., "John Smith" -> "john.smith")
 */
export function generateEmailPrefix(firstName: string, lastName: string): string {
  return `${firstName.toLowerCase()}.${lastName.toLowerCase()}`;
}

/**
 * Generate random sender names for inbox provisioning
 *
 * @param count Number of names to generate (max 10 for Hypertide)
 * @returns Array of SenderName objects
 */
export function generateRandomSenderNames(count: number = 10): SenderName[] {
  const names: SenderName[] = [];
  const usedPrefixes = new Set<string>();

  // Limit to 10 (Hypertide max)
  const targetCount = Math.min(count, 10);

  while (names.length < targetCount) {
    const firstName = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
    const lastName = LAST_NAMES[Math.floor(Math.random() * LAST_NAMES.length)];
    const emailPrefix = generateEmailPrefix(firstName, lastName);

    // Ensure unique combinations
    if (!usedPrefixes.has(emailPrefix)) {
      usedPrefixes.add(emailPrefix);
      names.push({
        firstName,
        lastName,
        emailPrefix,
        source: 'generated',
      });
    }
  }

  return names;
}

/**
 * Convert onboarding personas to sender names
 *
 * Extracts names from personas, generating last names if not provided.
 *
 * @param personas Array of OnboardingPersona from client onboarding
 * @param maxCount Maximum number of names to return
 * @returns Array of SenderName objects
 */
export function personasToSenderNames(
  personas: OnboardingPersona[],
  maxCount: number = 10
): SenderName[] {
  const names: SenderName[] = [];
  const usedPrefixes = new Set<string>();

  for (const persona of personas) {
    if (names.length >= maxCount) break;

    // Extract first name from persona
    let firstName = persona.first_name;
    if (!firstName && persona.name) {
      // Try to split full name
      const parts = persona.name.split(' ');
      firstName = parts[0];
    }
    if (!firstName && persona.job_title) {
      // Use job title to infer a generic name
      firstName = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
    }

    if (!firstName) continue;

    // Get or generate last name
    let lastName = persona.last_name;
    if (!lastName && persona.name) {
      const parts = persona.name.split(' ');
      lastName = parts.length > 1 ? parts[parts.length - 1] : undefined;
    }
    if (!lastName) {
      lastName = LAST_NAMES[Math.floor(Math.random() * LAST_NAMES.length)];
    }

    const emailPrefix = generateEmailPrefix(firstName, lastName);

    if (!usedPrefixes.has(emailPrefix)) {
      usedPrefixes.add(emailPrefix);
      names.push({
        firstName,
        lastName,
        emailPrefix,
        source: 'persona',
      });
    }
  }

  return names;
}

/**
 * Generate sender names for a client based on their onboarding data
 *
 * Priority:
 * 1. Custom names if provided
 * 2. Personas from onboarding
 * 3. Random generation to fill remaining slots
 *
 * @param onboardingData Client's onboarding data
 * @param count Number of names needed (default 10)
 * @returns Array of SenderName ready for Hypertide
 */
export function generateSenderNamesForClient(
  onboardingData?: {
    personas?: OnboardingPersona[];
    senderNamePreferences?: {
      usePersonas?: boolean;
      customNames?: SenderName[];
      nameCount?: number;
    };
    preGeneratedSenderNames?: SenderName[];
  },
  count: number = 10
): SenderName[] {
  const targetCount = Math.min(count, 10);
  const names: SenderName[] = [];
  const usedPrefixes = new Set<string>();

  // Helper to add name if unique
  const addName = (name: SenderName): boolean => {
    if (!usedPrefixes.has(name.emailPrefix) && names.length < targetCount) {
      usedPrefixes.add(name.emailPrefix);
      names.push(name);
      return true;
    }
    return false;
  };

  // 1. Use pre-generated names if available
  if (onboardingData?.preGeneratedSenderNames) {
    for (const name of onboardingData.preGeneratedSenderNames) {
      addName(name);
    }
  }

  // 2. Use custom names if provided
  if (onboardingData?.senderNamePreferences?.customNames) {
    for (const name of onboardingData.senderNamePreferences.customNames) {
      addName(name);
    }
  }

  // 3. Use personas if enabled (default true)
  const usePersonas = onboardingData?.senderNamePreferences?.usePersonas ?? true;
  if (usePersonas && onboardingData?.personas?.length) {
    const personaNames = personasToSenderNames(onboardingData.personas, targetCount);
    for (const name of personaNames) {
      addName(name);
    }
  }

  // 4. Fill remaining with random names
  if (names.length < targetCount) {
    const randomNames = generateRandomSenderNames(targetCount - names.length);
    for (const name of randomNames) {
      addName(name);
    }
  }

  return names;
}

/**
 * Calculate how many unique sender names are needed for a package
 *
 * Hypertide uses max 10 names per order, and names are reused across domains.
 * So even for Growth package (22 orders), we only need 10 names.
 *
 * @returns Always 10 (Hypertide max per order)
 */
export function getSenderNameCountForPackage(): number {
  // Hypertide allows max 10 users per order
  // Names are reused across all orders, so we always need exactly 10
  return 10;
}
