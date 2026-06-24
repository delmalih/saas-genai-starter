import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";
import { Analytics } from "@vercel/analytics/next";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const siteUrl = process.env.BETTER_AUTH_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  // Resolves relative OG/canonical URLs site-wide.
  metadataBase: new URL(siteUrl),
  title: {
    default: "SaaS GenAI Starter",
    template: "%s · SaaS GenAI Starter",
  },
  description:
    "Production-grade open-source SaaS starter for GenAI products: multi-tenancy, LLM cost tracking, observability, infra as code.",
  keywords: [
    "SaaS starter",
    "GenAI boilerplate",
    "Next.js FastAPI starter",
    "multi-tenant",
    "RAG template",
    "LLM cost tracking",
  ],
  openGraph: {
    type: "website",
    siteName: "SaaS GenAI Starter",
    title: "SaaS GenAI Starter",
    description:
      "Production-grade open-source SaaS starter for GenAI products: multi-tenancy, BYO-key LLM layer, RAG with citations, evals, $0 infra.",
    url: "/",
  },
  twitter: {
    card: "summary_large_image",
    title: "SaaS GenAI Starter",
    description:
      "Production-grade open-source SaaS starter for GenAI products — clone it and ship.",
  },
  alternates: { canonical: "/" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // Font variables live on <html>: globals.css applies font-family at the
    // html level, and CSS variables don't resolve upward from <body>.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body className="antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
        <Analytics />
      </body>
    </html>
  );
}
