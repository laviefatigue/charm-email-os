import type { Metadata } from "next";
import { Fraunces, Manrope, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/charm";
import { StoreProvider } from "@/components/providers/StoreProvider";
import { UserProvider } from "@/lib/contexts/UserContext";
import { Toaster } from "sonner";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["SOFT", "WONK", "opsz"],
  display: "swap",
});

const manrope = Manrope({
  variable: "--font-body",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Charm Email OS",
  description: "Operator control plane for client email infrastructure",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${fraunces.variable} ${manrope.variable} ${geistMono.variable} antialiased`}
      >
        <UserProvider>
          <StoreProvider>
            <AppShell>{children}</AppShell>
            <Toaster position="bottom-right" richColors />
          </StoreProvider>
        </UserProvider>
      </body>
    </html>
  );
}
