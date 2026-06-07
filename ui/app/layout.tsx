import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegLens",
  description: "Multi-agent regulatory compliance demo",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="header">
          <a href="/" className="brand">
            RegLens
          </a>
          <span className="tag">demo</span>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
