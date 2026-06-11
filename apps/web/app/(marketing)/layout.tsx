import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

export default function MarketingLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4">
          <Link href="/" className="font-heading font-semibold">
            saas-genai-starter
          </Link>
          <nav className="flex items-center gap-2">
            <ThemeToggle />
            <Button asChild variant="ghost">
              <Link href="/chat">Sign in</Link>
            </Button>
            <Button asChild>
              <Link href="/chat">Get started</Link>
            </Button>
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-6 text-sm text-muted-foreground">
          <span>MIT licensed</span>
          <a
            href="https://github.com/delmalih/saas-genai-starter"
            className="hover:text-foreground"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
