import { connection } from "next/server";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/client";

export async function ApiStatus() {
  // Render at request time — a build-time status would be frozen forever.
  await connection();
  let isUp = false;
  try {
    const { data } = await api.GET("/health", { cache: "no-store" });
    isUp = data?.status === "ok";
  } catch {
    isUp = false;
  }

  return (
    <span
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      title={isUp ? "API reachable" : "API unreachable"}
    >
      <span
        className={cn("size-2 rounded-full", isUp ? "bg-emerald-500" : "bg-red-500")}
      />
      API
    </span>
  );
}
