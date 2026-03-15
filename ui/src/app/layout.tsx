import type { Metadata } from "next";
import { Bebas_Neue, Special_Elite, Courier_Prime, Archivo_Black, Caveat } from "next/font/google";
import "./globals.css";

const bebasNeue = Bebas_Neue({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
});

const specialElite = Special_Elite({
  variable: "--font-typewriter",
  subsets: ["latin"],
  weight: "400",
});

const courierPrime = Courier_Prime({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "700"],
});

const archivoBlack = Archivo_Black({
  variable: "--font-stamp",
  subsets: ["latin"],
  weight: "400",
});

const caveat = Caveat({
  variable: "--font-handwritten",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
});

export const metadata: Metadata = {
  title: "Hive — Crowdsourced Agent Evolution",
  description: "Watch AI agents collaboratively evolve solutions in real-time",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${bebasNeue.variable} ${specialElite.variable} ${courierPrime.variable} ${archivoBlack.variable} ${caveat.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
