import { ConversationRail } from "@/components/chat/conversation-rail";

export default function ChatLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // Bleed the app shell's main padding: chat wants full-height columns.
    <div className="-m-6 flex h-[calc(100svh-3.5rem)]">
      <ConversationRail />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
