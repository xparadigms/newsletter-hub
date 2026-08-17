import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import Link from "next/link";
import NavBar, { LargeTitle } from "@/components/NavBar";
import ServiceWorker from "@/components/ServiceWorker";
import SwipeBack from "@/components/SwipeBack";
import TabBar from "@/components/TabBar";
import { SECTIONS, SITE } from "@/lib/config";
import { dataConnected } from "@/lib/posts";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-plex-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: {
    default: SITE.name,
    template: `%s — ${SITE.name}`,
  },
  description: SITE.description,
  applicationName: SITE.name,
  metadataBase: new URL(SITE.url),
  openGraph: {
    type: "website",
    siteName: SITE.name,
    title: SITE.name,
    description: SITE.description,
    images: ["/og.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE.name,
    description: SITE.description,
    images: ["/og.png"],
  },
  manifest: "/manifest.webmanifest",
  // Lets iOS install it to the Home Screen and launch without browser chrome.
  appleWebApp: {
    capable: true,
    title: SITE.name,
    // Full-bleed under the status bar; the nav bar pads itself with
    // env(safe-area-inset-top) so it clears the clock / Dynamic Island.
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
  other: {
    // Next emits the modern mobile-web-app-capable; iOS before 17 still needs
    // Apple's legacy tag to launch from the Home Screen without browser chrome.
    "apple-mobile-web-app-capable": "yes",
    // Single tag, rewritten by the boot script and the theme toggle so the
    // status bar tracks the chosen theme rather than the system one.
    "theme-color": "#ffffff",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Lets the app run under the status bar and home indicator; every fixed
  // element then pays that back with env(safe-area-inset-*).
  viewportFit: "cover",
  // Zoom stays available — user-scalable=no is an accessibility anti-pattern.
  maximumScale: 5,
};

// Runs before first paint: applies the persisted (or system) theme and the
// persisted translation-filter setting, so neither flashes on load, and tints
// the status bar to match. theme-color is set here rather than via the
// prefers-color-scheme metadata because a manual theme choice must win.
const bootScript = `(function(){try{var d=document.documentElement,t=localStorage.getItem("theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";d.setAttribute("data-theme",t);var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content",t==="dark"?"#0d0d0d":"#ffffff");var l=localStorage.getItem("langs");if(l==="en"||l==="all"||l==="ja-ko")d.setAttribute("data-langs",l);d.setAttribute("data-story",localStorage.getItem("story-mode")==="on"?"on":"off");}catch(e){}})();`;

// iOS picks a launch image by matching device-width/height and pixel ratio;
// without one it shows a blank white screen while the app boots.
const SPLASH_DEVICES = [
  { w: 320, h: 568, r: 2 },
  { w: 375, h: 667, r: 2 },
  { w: 390, h: 844, r: 3 },
  { w: 393, h: 852, r: 3 },
  { w: 402, h: 874, r: 3 },
  { w: 414, h: 896, r: 2 },
  { w: 428, h: 926, r: 3 },
  { w: 430, h: 932, r: 3 },
  { w: 440, h: 956, r: 3 },
];

function SplashLinks() {
  return (
    <>
      {SPLASH_DEVICES.flatMap((d) =>
        (["light", "dark"] as const).map((theme) => (
          <link
            key={`${d.w}x${d.h}-${theme}`}
            rel="apple-touch-startup-image"
            href={`/splash/splash-${d.w}x${d.h}-${theme}.png`}
            media={`(prefers-color-scheme: ${theme}) and (device-width: ${d.w}px) and (device-height: ${d.h}px) and (-webkit-device-pixel-ratio: ${d.r})`}
          />
        ))
      )}
    </>
  );
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // Font variables must live on <html>: globals.css declares --font-sans on
    // :root, and var() inside it resolves against that same element.
    <html
      lang="en"
      className={`${archivo.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <SplashLinks />
      </head>
      <body>
        <script dangerouslySetInnerHTML={{ __html: bootScript }} />
        <ServiceWorker />
        <NavBar />
        {!dataConnected && (
          <div className="notice">
            <div className="container">
              <p>Set NOTION_TOKEN to load content from the Notion databases</p>
            </div>
          </div>
        )}
        <SwipeBack />
        <main id="app-main">
          <LargeTitle />
          {children}
        </main>
        <TabBar />
        <footer className="site-footer">
          <div className="container site-footer__inner">
            <div>
              <div className="site-footer__brand">{SITE.name}</div>
              <p className="site-footer__note">{SITE.tagline}</p>
            </div>
            <nav className="site-footer__nav">
              {SECTIONS.map((s) => (
                <Link key={s.key} href={`/section/${s.key}`}>
                  {s.label}
                </Link>
              ))}
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
