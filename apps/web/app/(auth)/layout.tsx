import Link from "next/link";

export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 p-4">
      <Link href="/" className="font-heading text-lg font-semibold">
        saas-genai-starter
      </Link>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
