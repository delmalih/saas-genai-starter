"use client";

import { useSession } from "@/lib/auth-client";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function ProfileCard() {
  const { data: session, isPending } = useSession();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your account, managed by the auth service</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending || !session ? (
          <Skeleton className="h-10 w-64" />
        ) : (
          <dl className="grid max-w-md grid-cols-[6rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted-foreground">Name</dt>
            <dd className="font-medium">{session.user.name}</dd>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="font-medium">{session.user.email}</dd>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
