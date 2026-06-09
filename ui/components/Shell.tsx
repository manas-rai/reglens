"use client";

import clsx from "clsx";
import {
  FileText,
  LayoutDashboard,
  Library,
  Settings as SettingsIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/runs", label: "Runs", icon: FileText },
  { href: "/policies", label: "Policies", icon: Library },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-block">
          <Link href="/" className="brand">
            RegLens
          </Link>
          <span className="tag">demo</span>
        </div>
        <nav>
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={clsx("nav-item", active && "active")}
              >
                <Icon size={16} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
