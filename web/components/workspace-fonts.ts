import { EB_Garamond } from "next/font/google";

// The workspace headings use the landing page's display face.
export const garamond = EB_Garamond({
  variable: "--font-garamond",
  subsets: ["latin"],
  weight: ["500"],
  display: "swap",
});
