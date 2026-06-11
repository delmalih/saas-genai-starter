import { Suspense } from "react";
import { ApiStatus } from "@/components/api-status";
import { AppSidebar } from "@/components/app-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export default function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex min-h-svh">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-3 border-b px-4">
          <Suspense>
            <ApiStatus />
          </Suspense>
          <ThemeToggle />
          {/* Real user menu lands with auth (SGS-010) */}
          <Avatar className="size-8">
            <AvatarFallback>ME</AvatarFallback>
          </Avatar>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
