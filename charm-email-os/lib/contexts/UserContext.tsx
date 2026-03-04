'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

interface User {
  email: string;
  displayName: string;
  initials: string;
  authenticated: boolean;
}

interface UserContextType {
  user: User | null;
  isLoading: boolean;
  signOut: () => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch('/api/auth/user')
      .then(res => res.json())
      .then(data => {
        if (data.authenticated) {
          setUser(data);
          // Store email in sessionStorage for API calls
          if (typeof window !== 'undefined') {
            sessionStorage.setItem('user_email', data.email);
          }
        }
        setIsLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch user:', err);
        setIsLoading(false);
      });
  }, []);

  const signOut = () => {
    // Clear session storage
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('user_email');
    }

    // Check if we're in local development (localhost or 127.0.0.1)
    const isLocalDev = typeof window !== 'undefined' &&
      (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

    if (isLocalDev) {
      // In local dev, just clear state and reload (no Cloudflare logout available)
      setUser(null);
      window.location.href = '/';
    } else {
      // In production, use Cloudflare Access logout URL
      // This clears the CF_Authorization cookie and redirects to IDP logout
      window.location.href = `/cdn-cgi/access/logout?returnTo=${encodeURIComponent(window.location.origin)}`;
    }
  };

  return (
    <UserContext.Provider value={{ user, isLoading, signOut }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
}
