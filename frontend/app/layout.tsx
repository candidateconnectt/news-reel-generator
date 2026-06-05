import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reel Generator",
  description: "Autonomous News Reel Generator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen antialiased">{children}</body>
    </html>
  );
}
