import { Inter } from 'next/font/google';
import type { Metadata } from 'next';
import './globals.css';
import "flatpickr/dist/flatpickr.css";
import { SidebarProvider } from '@/context/SidebarContext';
import { ThemeProvider } from '@/context/ThemeContext';

export const metadata: Metadata = {
  title: {
    default: "Stock Picker AI",
    template: "%s | Stock Picker AI",
  },
  description:
    "Momentum + sentiment + fundamentals research tool with a backtested Signal Book. Not investment advice.",
  // Served statically from /public so Next 16's metadata image loader (which
  // crashes on some SVGs) never touches it.
  icons: { icon: "/icon.svg" },
};

const inter = Inter({
  subsets: ["latin"],
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: the ThemeProvider toggles the `dark` class on
    // <html> on the client, and browser extensions inject attributes into
    // <html>/<body> before React hydrates. Both are intended/unavoidable
    // root-element differences, so we tell React not to warn about them.
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.className} dark:bg-gray-900`}
        suppressHydrationWarning
      >
        <ThemeProvider>
          <SidebarProvider>{children}</SidebarProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
