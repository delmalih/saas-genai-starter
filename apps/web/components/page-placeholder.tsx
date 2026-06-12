interface PagePlaceholderProps {
  title: string;
  description: string;
  ticket: string;
}

export function PagePlaceholder({ title, description, ticket }: PagePlaceholderProps) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      <p className="text-muted-foreground">{description}</p>
      <p className="text-sm text-muted-foreground">Coming in {ticket}.</p>
    </div>
  );
}
