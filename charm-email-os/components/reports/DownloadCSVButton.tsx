'use client';

import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface DownloadCSVButtonProps {
  url: string;
  filename: string;
  disabled?: boolean;
}

/**
 * Triggers a CSV download via fetch+blob (rather than just <a download>) so
 * the X-User-Email header from the API client wrapper is preserved. The
 * server-side filename in Content-Disposition is the canonical one; this
 * component's `filename` is the fallback when the header isn't readable.
 */
export function DownloadCSVButton({ url, filename, disabled = false }: DownloadCSVButtonProps) {
  async function onClick() {
    const userEmail =
      typeof window !== 'undefined' ? sessionStorage.getItem('user_email') : null;
    const res = await fetch(url, {
      headers: userEmail ? { 'X-User-Email': userEmail } : {},
    });
    if (!res.ok) {
      console.error(`CSV download failed: ${res.status} ${res.statusText}`);
      return;
    }
    const blob = await res.blob();
    const objectUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(objectUrl);
  }

  return (
    <Button onClick={onClick} disabled={disabled} variant="outline" size="sm">
      <Download className="mr-1.5 h-3.5 w-3.5" />
      Download CSV
    </Button>
  );
}
