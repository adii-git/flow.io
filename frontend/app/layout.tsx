
import "./globals.css";
import type { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth";
import RouteProgress from "@/components/RouteProgress";

export const metadata = {
  title: "flow.io",
  description: "Flow.io — AI, in flow.",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,300..800&display=swap"
        />
      </head>

      <body className="font-sans antialiased">
        {/* Shared background across every page */}
        <div className="global-scene" aria-hidden="true">
          <div className="global-scene-image" />
          <div className="global-scene-vignette" />

          <div className="global-monitor-glow" />
          <div className="global-monitor-flicker" />

          <div className="global-grass-sparkles">
            {Array.from({ length: 24 }, (_, i) => (
              <span
                key={i}
                style={{
                  left: `${(i * 37 + 13) % 100}%`,
                  top: `${(i * 53 + 17) % 100}%`,
                  animationDelay: `${(i % 8) * -0.6}s`,
                }}
              />
            ))}
          </div>
        </div>

        {/* Application pages render above the background */}
        <RouteProgress />
        <div className="global-content">
          <AuthProvider>{children}</AuthProvider>
        </div>
      </body>
    </html>
  );
}
