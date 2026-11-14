import Link from "next/link";
import CuesMark from "@/components/cues-mark";

// Site footer, laid out like LionPlan's: brand and a line about Cues, then
// three link columns.
export default function LandingFooter({ start }: { start: string }) {
  const columns = [
    {
      title: "Product",
      links: [
        { label: "How it works", href: "#how" },
        { label: "Teacher control", href: "#control" },
        { label: "Get started", href: start },
      ],
    },
    {
      title: "About",
      links: [
        { label: "Privacy", href: "#privacy" },
        { label: "FAQ", href: "#faq" },
      ],
    },
    {
      title: "Teachers",
      links: [
        { label: "Sign in", href: "/login" },
        { label: "Open the classroom", href: "/dashboard" },
      ],
    },
  ];
  return (
    <footer className="ln-site-footer">
      <div className="ln-footer-top">
        <div className="ln-footer-brand">
          <Link href="/" className="ln-brand" aria-label="Cues home">
            <CuesMark className="ln-brand-mark" size={30} />
          </Link>
          <p>
            Classroom support for special-education teachers. Built by a student
            team.
          </p>
        </div>
        {columns.map((column) => (
          <nav key={column.title} aria-label={column.title}>
            <h2>{column.title}</h2>
            <ul>
              {column.links.map((link) => (
                <li key={link.label}>
                  {link.href.startsWith("#") ? (
                    <a href={link.href}>{link.label}</a>
                  ) : (
                    <Link href={link.href}>{link.label}</Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
    </footer>
  );
}
