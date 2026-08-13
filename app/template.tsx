// template.tsx remounts on every navigation, which is what lets the page
// animate in. Direction comes from <html data-nav>, set by lib/nav.ts.
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-transition">{children}</div>;
}
