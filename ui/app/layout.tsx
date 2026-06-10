import type { Metadata } from "next";
import { KeyboardShortcuts } from "@/components/KeyboardShortcuts";
import { Shell } from "@/components/Shell";
import { ToastProvider } from "@/components/Toasts";
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
        <ToastProvider>
          <Shell>{children}</Shell>
          <KeyboardShortcuts />
        </ToastProvider>
      </body>
    </html>
  );
}
