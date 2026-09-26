import type { SVGProps } from "react";

/**
 * The suite's line icons.
 *
 * Emoji were doing this job — 🔒 🔑 ✉ 📅 📍 🔓 🔔 ☀ 🌙 ⚠, twenty-four of them. They are not
 * a typeface we chose: each platform draws its own, at its own weight, in its own colours. The
 * same lock is grey and flat on one machine and a glossy yellow padlock on another, and neither
 * follows the accent or the text colour beside it. On a product sold on how it looks, the one
 * element we did not control was the one repeated on every screen.
 *
 * Drawn rather than picked so nothing new is vendored, and stroked in `currentColor` so an icon
 * inherits whatever colour its text has — muted in a caption, accent in a link, amber in a
 * warning — without a single prop.
 *
 * `aria-hidden` by default: every one of these sits beside a label that already says it. An icon
 * that repeats its own label reads it twice to a screen reader. Pass `aria-hidden={false}` with a
 * title only if one ever stands alone.
 */
// `inline-block` and a nudged baseline so an icon dropped straight into a line of text sits on it,
// rather than hanging below as a block-level SVG does. `shrink-0` because most of these live in a
// flex row next to a label that is allowed to truncate; the icon is not.
function Icon({
  children,
  className = "inline-block h-4 w-4 shrink-0 align-[-0.15em]",
  ...rest
}: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
      {...rest}
    >
      {children}
    </svg>
  );
}

export function LockIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <rect x="4" y="10.5" width="16" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </Icon>
  );
}

/** The same body with the shackle swung clear — the two must be tellable apart at 16px. */
export function UnlockIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <rect x="4" y="10.5" width="16" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 7.7-1.5" />
    </Icon>
  );
}

export function KeyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <circle cx="7.5" cy="15.5" r="3.5" />
      <path d="M10 13 20 3" />
      <path d="M17.5 5.5 19.5 7.5" />
      <path d="M15 8 17 10" />
    </Icon>
  );
}

export function MailIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
      <path d="m3.8 7 7.1 5.3a2 2 0 0 0 2.2 0L20.2 7" />
    </Icon>
  );
}

export function CalendarIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
      <path d="M3.5 9.5h17" />
      <path d="M8 3.5v3M16 3.5v3" />
    </Icon>
  );
}

export function PinIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M12 21s6.5-6.1 6.5-10.5a6.5 6.5 0 1 0-13 0C5.5 14.9 12 21 12 21Z" />
      <circle cx="12" cy="10.5" r="2.4" />
    </Icon>
  );
}

export function BellIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M18 16.5V11a6 6 0 1 0-12 0v5.5L4.5 18.5h15L18 16.5Z" />
      <path d="M10 21.5h4" />
    </Icon>
  );
}

export function SunIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6" />
    </Icon>
  );
}

export function MoonIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M20 14.2A8.4 8.4 0 0 1 9.8 4 8.5 8.5 0 1 0 20 14.2Z" />
    </Icon>
  );
}

export function WarningIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M12 4.2 21.2 20H2.8L12 4.2Z" />
      <path d="M12 10v4.2" />
      <path d="M12 17.3h.01" />
    </Icon>
  );
}
