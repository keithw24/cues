import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cues · Teacher dashboard",
  description: "A clear view of classroom task activity and seat observations.",
  icons: { icon: "/icon.svg" },
  other: { "page-type": "software", "site-kind": "software" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-type="software"
      data-scroll-behavior="smooth"
      className={`${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <a className="skip-link" href="#main-content">
          Skip to classroom monitoring
        </a>
        {children}
      </body>
    </html>
  );
}
