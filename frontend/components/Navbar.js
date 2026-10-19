"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mic, LayoutDashboard, PlusCircle, Upload, Stethoscope } from "lucide-react";

export default function Navbar() {
  const pathname = usePathname();

  const isMeetings = pathname.startsWith("/meetings");
  return (
    <header className="actionmic-header">
      <div className="actionmic-nav-inner">
        <Link href="/meetings" className="actionmic-brand">
          <div className="actionmic-logo-icon">
            <Mic size={20} className="actionmic-mic-svg" />
            <span className="actionmic-pulse-ring"></span>
          </div>
          <div className="actionmic-brand-text">
            <span className="actionmic-brand-title">ActionMic<span className="brand-accent">.AI</span></span>
            <span className="actionmic-brand-subtitle">Meeting Intelligence Platform</span>
          </div>
        </Link>

        <nav className="actionmic-nav-links">
          <Link
            href="/meetings"
            className={`actionmic-nav-item ${pathname === "/meetings" || pathname === "/" ? "active" : ""}`}
          >
            <LayoutDashboard size={16} />
            <span>Dashboard</span>
          </Link>
          <Link
            href="/meetings/upload"
            className={`actionmic-nav-item ${pathname === "/meetings/upload" ? "active" : ""}`}
          >
            <Upload size={16} />
            <span>Upload Recording</span>
          </Link>
        </nav>

        <div className="actionmic-nav-actions">
          <Link href="/meetings?new=1" className="btn-primary-glow">
            <PlusCircle size={16} />
            <span>New Meeting</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
