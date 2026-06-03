import type { Metadata } from "next"
import Link from "next/link"
import "./globals.css"

export const metadata: Metadata = {
  title: "RealitySync",
  description: "Geospatial boundary validation and data curation platform",
}

function AuthStatus() {
  return (
    <div id="auth-status" className="flex items-center gap-3 text-sm">
      <script
        dangerouslySetInnerHTML={{
          __html: `
            (function() {
              var u = JSON.parse(localStorage.getItem('realitysync_user') || 'null');
              var el = document.getElementById('auth-status');
              if (!el) return;
              if (u && u.name) {
                el.innerHTML = '<span class="text-gray-500">' + u.name + '</span>' +
                  '<a href="/login" onclick="localStorage.clear();" class="text-gray-400 hover:text-gray-600">Logout</a>';
              } else {
                el.innerHTML = '<a href="/login" class="text-blue-600 hover:text-blue-800">Sign In</a>';
              }
            })();
          `,
        }}
      />
    </div>
  )
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900">
        <header className="border-b border-gray-200 bg-white px-6 py-3">
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <Link href="/" className="text-xl font-bold text-blue-700">
              RealitySync
            </Link>
            <nav className="flex gap-6 text-sm font-medium">
              <Link href="/" className="hover:text-blue-600">Map</Link>
              <Link href="/upload" className="hover:text-blue-600">Upload</Link>
              <Link href="/dashboard" className="hover:text-blue-600">Triage</Link>
              <Link href="/initiatives" className="hover:text-blue-600">Initiatives</Link>
              <Link href="/marketplace" className="hover:text-blue-600">Marketplace</Link>
              <Link href="/exports" className="hover:text-blue-600">Exports</Link>
              <Link href="/credits" className="hover:text-blue-600">Credits</Link>
            </nav>
            <AuthStatus />
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  )
}
