"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/map", label: "Find Spots" },
  { href: "/advertising", label: "Sponsors" },
  { href: "/vendors", label: "Vendors" },
  { href: "/city", label: "Cities" },
] as const;

export function PlatformNav() {
  const pathname = usePathname();

  return (
    <header className="brut-border-b bg-brut-yellow sticky top-0 z-30">
      <div className="flex flex-wrap items-center gap-4 px-4 py-3 md:px-6">
        <Link href="/" className="mr-auto min-w-0">
          <p className="text-lg font-extrabold uppercase leading-none tracking-tight md:text-xl">
            City as Venue
          </p>
          <p className="mt-0.5 text-xs font-semibold md:text-sm">
            World Cup watch party finder
          </p>
        </Link>
        <nav className="flex flex-wrap items-center gap-2">
          {NAV_ITEMS.map(({ href, label }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`brut-btn !min-h-9 !px-3 !py-2 !text-xs md:!text-sm ${
                  active ? "brut-btn-active" : ""
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
