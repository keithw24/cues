import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { isEnabled } from "@/lib/flags";
import { themeScript } from "@/lib/theme";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cues",
  description: "A clear view of classroom task activity and seat observations.",
  other: { "page-type": "software", "site-kind": "software" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-type="software"
      data-scroll-behavior="smooth"
      className={`${inter.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      {isEnabled("web.theme_toggle") ? (
        <head>
          <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        </head>
      ) : null}
      <body className="min-h-full flex flex-col">
        <a className="skip-link" href="#main-content">
          Skip to classroom monitoring
        </a>
        {children}
      </body>
    </html>
  );
}
