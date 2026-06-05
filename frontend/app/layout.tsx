import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono, Instrument_Serif } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import Nav from "@/components/Nav";
import { ApiStatus } from "@/components/ApiStatus";

const sans = IBM_Plex_Sans({
  weight: ["300", "400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const display = Instrument_Serif({
  weight: ["400"],
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Reel — Autonomous News Shorts",
  description:
    "Turn a topic into a vertical short-form video. Topic → Gemini script → Pexels stock → edge-tts voiceover → stitched MP4.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} ${display.variable}`}
    >
      <body className="min-h-screen bg-[var(--bg)] text-[var(--text)] antialiased">
        {/* Layered background: gradient + grain texture. Both pointer-events:none, fixed. */}
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 z-0"
          style={{
            background:
              "radial-gradient(1200px 600px at 85% -10%, rgba(225,6,0,0.10), transparent 60%)," +
              "radial-gradient(900px 500px at -10% 110%, rgba(225,6,0,0.06), transparent 65%)",
          }}
        />
        <div aria-hidden className="grain pointer-events-none fixed inset-0 z-0" />

        <div className="relative z-10 flex min-h-screen flex-col">
          <header className="sticky top-0 z-40 border-b border-[var(--border)]/60 bg-[var(--bg)]/70 backdrop-blur-xl">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-3.5">
              <Link href="/" className="group flex items-baseline gap-2.5">
                <span
                  className="font-display text-[28px] leading-none tracking-tight"
                  style={{ fontStyle: "italic" }}
                >
                  Reel
                </span>
                <span className="text-[var(--brand)] text-[28px] leading-none">.</span>
                <span className="hidden md:inline-block font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-dim)] group-hover:text-[var(--text-muted)] transition-colors">
                  autonomous news shorts
                </span>
              </Link>
              <Nav />
              <ApiStatus />
            </div>
          </header>

          <main className="flex-1">{children}</main>

          <footer className="border-t border-[var(--border)]/60 mt-24">
            <div className="mx-auto max-w-7xl px-6 py-8 flex items-center justify-between text-[11px] font-mono uppercase tracking-[0.18em] text-[var(--text-dim)]">
              <span>Reel · MVP build</span>
              <span className="hidden sm:inline">stock-stitch pipeline · v0.1</span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
