"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Generate" },
  { href: "/history", label: "History" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex items-center gap-7">
      {TABS.map((t) => {
        const active = t.href === "/" ? pathname === "/" : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? "page" : undefined}
            className="nav-link"
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
