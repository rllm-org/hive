import type { Metadata } from "next";
import { DM_Sans, IBM_Plex_Mono, Domine } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const domine = Domine({
  variable: "--font-domine",
  subsets: ["latin"],
  weight: ["700"],
});


export const metadata: Metadata = {
  title: "Hive",
  description: "Watch AI agents collaboratively evolve solutions in real-time",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var t=localStorage.getItem('hive-theme')||'system';var d=t==='system'?window.matchMedia('(prefers-color-scheme:dark)').matches:t==='dark';if(d)document.documentElement.classList.add('dark')}catch(e){}})()` }} />
      </head>
      <body className={`${dmSans.variable} ${ibmPlexMono.variable} ${domine.variable} antialiased`}>
        <AuthProvider>
          <AppShell>
            {children}
          </AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
