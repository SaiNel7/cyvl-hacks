import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import { PlatformNav } from "@/components/layout/PlatformNav";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: "City as Venue — Watch Party Finder",
  description:
    "Find and score the best public spots in Somerville to host a World Cup watch party.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${spaceGrotesk.className} antialiased`}>
        <div className="flex min-h-screen flex-col bg-brut-white">
          <PlatformNav />
          <main className="flex min-h-0 flex-1 flex-col">{children}</main>
        </div>
      </body>
    </html>
  );
}
