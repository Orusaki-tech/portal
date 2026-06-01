import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "RealitySync",
  description: "Geospatial boundary validation and data curation platform",
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
            <a href="/" className="text-xl font-bold text-blue-700">
              RealitySync
            </a>
            <nav className="flex gap-6 text-sm font-medium">
              <a href="/" className="hover:text-blue-600">Map</a>
              <a href="/dashboard" className="hover:text-blue-600">Triage</a>
              <a href="/initiatives" className="hover:text-blue-600">Initiatives</a>
              <a href="/marketplace" className="hover:text-blue-600">Marketplace</a>
              <a href="/exports" className="hover:text-blue-600">Exports</a>
              <a href="/credits" className="hover:text-blue-600">Credits</a>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  )
}
