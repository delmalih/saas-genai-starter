"use client";

import {
  BarChart3Icon,
  FileTextIcon,
  MessageSquareIcon,
  SettingsIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquareIcon },
  { href: "/documents", label: "Documents", icon: FileTextIcon },
  { href: "/usage", label: "Usage", icon: BarChart3Icon },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
] as const;

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-56 shrink-0 border-r md:flex md:flex-col">
      <div className="flex h-14 items-center border-b px-4">
        {/* Org switcher lands here (SGS-015) */}
        <Link href="/" className="truncate font-semibold">
          saas-genai-starter
        </Link>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <item.icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
