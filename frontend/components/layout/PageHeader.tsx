interface PageHeaderProps {
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 brut-border-b bg-brut-yellow px-4 py-6 md:px-8">
      <div>
        <h1 className="text-2xl font-extrabold uppercase tracking-tight md:text-4xl">
          {title}
        </h1>
        <p className="mt-2 max-w-2xl text-sm font-semibold md:text-base">
          {subtitle}
        </p>
      </div>
      {action}
    </div>
  );
}
