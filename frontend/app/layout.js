import "./globals.css";

export const metadata = {
  title: "ActionMic_AI — Meeting Intelligence Platform",
  description: "AI-powered meeting recording, transcription, translation, decisions, and action items for Google Meet, Zoom, WhatsApp, Teams, and in-person meetings.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
