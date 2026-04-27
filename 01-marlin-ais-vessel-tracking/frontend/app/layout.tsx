import type { Metadata } from 'next';
import 'leaflet/dist/leaflet.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'MARLIN — Maritime Anomaly & Risk Intelligence Layer',
  description: 'On-prem maritime intel for INDOPACOM contested logistics. Powered by Kamiwaza.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
