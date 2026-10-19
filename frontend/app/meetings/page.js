"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "@/components/Navbar";
import {
  listMeetings,
  createMeeting,
  deleteMeeting
} from "@/lib/api";
import {
  Mic,
  Upload,
  Calendar,
  Clock,
  Users,
  Search,
  Filter,
  Trash2,
  ChevronRight,
  Sparkles,
  CheckCircle2,
  Radio,
  RefreshCw,
  FileAudio,
  Video,
  Wifi,
  BriefcaseBusiness,
  ArrowUpRight,
  Layers
} from "lucide-react";

function MeetingsDashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [totalMeetingsCount, setTotalMeetingsCount] = useState(0);
  const [showModal, setShowModal] = useState(false);

  // Form state
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("en");
  const [creating, setCreating] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [meetingMode, setMeetingMode] = useState("online");
  const [platform, setPlatform] = useState("google_meet");

  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setShowModal(true);
    }
  }, [searchParams]);

  useEffect(() => {
    fetchMeetings();
  }, [statusFilter, sourceFilter, page]);

  async function fetchMeetings() {
    setLoading(true);
    try {
      const data = await listMeetings({
        page,
        search,
        status: statusFilter === "all" ? "" : statusFilter,
        sourceType: sourceFilter === "all" ? "" : sourceFilter
      });
      setMeetings(data.items || []);
      setTotalMeetingsCount(data.total || 0);
    } catch (err) {
      console.error("Failed to load meetings:", err);
    } finally {
      setLoading(false);
    }
  }

  function handleSearch(e) {
    e.preventDefault();
    setPage(1);
    fetchMeetings();
  }

  async function handleCreate(mode = "record") {
    if (!newTitle.trim()) {
      setErrorMsg("Please enter a meeting title");
      return;
    }
    setCreating(true);
    setErrorMsg(null);
    try {
      const meeting = await createMeeting({
        title: newTitle.trim(),
        description: newDesc.trim() || null,
        source_language: sourceLang,
        target_language: targetLang,
        source_type: mode === "upload" ? "upload" : "live",
        platform: meetingMode === "offline" ? "in_person" : platform
      });

      setShowModal(false);
      setNewTitle("");
      setNewDesc("");

      if (mode === "upload") {
        router.push(`/meetings/${meeting.id}?tab=upload`);
      } else {
        router.push(`/meetings/${meeting.id}/record`);
      }
    } catch (err) {
      setErrorMsg(err.message || "Failed to create meeting");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(e, meetingId) {
    e.stopPropagation();
    e.preventDefault();
    if (!confirm("Are you sure you want to delete this meeting?")) return;
    try {
      await deleteMeeting(meetingId);
      setMeetings(meetings.filter((m) => m.id !== meetingId));
    } catch (err) {
      alert("Failed to delete meeting: " + err.message);
    }
  }

  // Metrics
  const totalMeetings = meetings.length;
  const completedMeetings = meetings.filter((m) => m.status === "completed" || m.processing_status === "completed").length;
  const activeMeetings = meetings.filter((m) => m.recording_status === "recording").length;

  return (
    <div className="actionmic-page">
      <Navbar />

      <main className="actionmic-container">
        {/* Top Hero Banner */}
        <div className="dashboard-hero">
          <div className="hero-content">
            <div className="hero-badge">
              <Sparkles size={14} className="sparkle-icon" />
              <span>AI-Powered Intelligence Engine Active</span>
            </div>
            <h1 className="hero-heading">Meeting Intelligence Workspace</h1>
            <p className="hero-subtext">
              Record multilingual discussions, capture real-time transcripts, transliterate Indic speech,
              and automatically extract decisions, action items, and schedules.
            </p>
          </div>

          <div className="hero-quick-actions meeting-entry-options">
            <button onClick={() => { setMeetingMode("online"); setShowModal(true); }} className="hero-action-btn primary">
              <Wifi size={18} /><span>Record Online Meeting</span>
            </button>
            <button onClick={() => { setMeetingMode("offline"); setShowModal(true); }} className="hero-action-btn secondary">
              <BriefcaseBusiness size={18} /><span>Record Offline Meeting</span>
            </button>
            <Link href="/meetings/upload?mode=video" className="hero-action-btn secondary">
              <Video size={18} /><span>Convert Video to Audio</span>
            </Link>
            <Link href="/meetings/upload?mode=audio" className="hero-action-btn secondary">
              <FileAudio size={18} /><span>Upload Audio & Process</span>
            </Link>
          </div>
        </div>

        {/* Stats Strip */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon-wrapper bg-blue">
              <Layers size={20} />
            </div>
            <div className="stat-info">
              <span className="stat-value">{totalMeetings}</span>
              <span className="stat-label">Total Meetings</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon-wrapper bg-emerald">
              <CheckCircle2 size={20} />
            </div>
            <div className="stat-info">
              <span className="stat-value">{completedMeetings}</span>
              <span className="stat-label">Processed & Ready</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon-wrapper bg-red">
              <Radio size={20} className={activeMeetings > 0 ? "pulse-icon" : ""} />
            </div>
            <div className="stat-info">
              <span className="stat-value">{activeMeetings}</span>
              <span className="stat-label">Active Recordings</span>
            </div>
          </div>
        </div>

        {/* Controls Bar: Search & Status Filters */}
        <div className="controls-bar">
          <form onSubmit={handleSearch} className="search-box">
            <Search size={18} className="search-icon" />
            <input
              type="text"
              placeholder="Search meetings by title, topic, or keyword..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="search-input"
            />
          </form>

          <button onClick={fetchMeetings} className="filter-pill" disabled={loading} title="Refresh meetings">
            <RefreshCw size={14} className={loading ? "spin-icon" : ""} /> Refresh
          </button>

          <div className="filter-pills">
            {["all", "completed", "active", "draft"].map((status) => (
              <button
                key={status}
                onClick={() => { setStatusFilter(status); setPage(1); }}
                className={`filter-pill ${statusFilter === status ? "active" : ""}`}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>
          <div className="filter-pills source-filter-pills">
            {["all", "live", "upload"].map((source) => (
              <button
                key={source}
                onClick={() => { setSourceFilter(source); setPage(1); }}
                className={`filter-pill ${sourceFilter === source ? "active" : ""}`}
              >
                {source === "all" ? "All sources" : source === "live" ? "Recorded" : "Uploaded"}
              </button>
            ))}
          </div>
        </div>

        {totalMeetingsCount > 50 && (
          <div className="pagination-bar">
            <span>Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, totalMeetingsCount)} of {totalMeetingsCount}</span>
            <div className="pagination-actions">
              <button className="filter-pill" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Previous</button>
              <span>Page {page} of {Math.ceil(totalMeetingsCount / 50)}</span>
              <button className="filter-pill" disabled={page >= Math.ceil(totalMeetingsCount / 50)} onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          </div>
        )}

        {/* Meetings List */}
        {loading ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading meeting intelligence records...</p>
          </div>
        ) : meetings.length === 0 ? (
          <div className="empty-state-card">
            <div className="empty-icon-wrap">
              <FileAudio size={42} />
            </div>
            <h3>No meetings found</h3>
            <p>Get started by recording a live meeting or uploading an audio conversation.</p>
            <div className="empty-actions">
              <button onClick={() => setShowModal(true)} className="btn-primary-glow">
                <Mic size={16} /> Record First Meeting
              </button>
            </div>
          </div>
        ) : (
          <div className="meetings-grid">
            {meetings.map((meeting) => (
              <Link
                key={meeting.id}
                href={`/meetings/${meeting.id}`}
                className="meeting-card"
              >
                <div className="meeting-card-header">
                  <div className="meeting-title-row">
                    <h3 className="meeting-title">{meeting.title}</h3>
                    <span className={`status-pill ${meeting.recording_status === "recording" ? "recording" : meeting.processing_status}`}>
                      {meeting.recording_status === "recording" ? "● Recording" : meeting.processing_status || meeting.status}
                    </span>
                  </div>
                  {meeting.description && (
                    <p className="meeting-desc">{meeting.description}</p>
                  )}
                </div>

                <div className="meeting-card-meta">
                  <div className="meta-item">
                    <Calendar size={14} />
                    <span>{meeting.meeting_date ? new Date(meeting.meeting_date).toLocaleDateString() : "Today"}</span>
                  </div>
                  {meeting.duration_seconds > 0 && (
                    <div className="meta-item">
                      <Clock size={14} />
                      <span>{Math.round(meeting.duration_seconds)}s</span>
                    </div>
                  )}
                  <div className="meta-item">
                    <Users size={14} />
                    <span>{meeting.speaker_count || 1} Speakers</span>
                  </div>
                </div>

                <div className="meeting-card-footer">
                  <span className="lang-tag">
                    {meeting.source_language?.toUpperCase() || "AUTO"} → {meeting.target_language?.toUpperCase() || "EN"}
                  </span>
                  <div className="card-action-btns">
                    <button
                      onClick={(e) => handleDelete(e, meeting.id)}
                      className="icon-action-btn delete"
                      title="Delete meeting"
                    >
                      <Trash2 size={16} />
                    </button>
                    <span className="open-link">
                      Open <ArrowUpRight size={14} />
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* New Meeting Modal */}
        {showModal && (
          <div className="modal-backdrop" onClick={() => setShowModal(false)}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2>{meetingMode === "offline" ? "Record Offline Meeting" : "Record Online Meeting"}</h2>
                <button onClick={() => setShowModal(false)} className="close-btn">×</button>
              </div>

              {errorMsg && <div className="modal-error">{errorMsg}</div>}

              <div className="modal-body">
                <div className="form-group">
                  <label>Meeting Title *</label>
                  <input
                    type="text"
                    placeholder="e.g. Q3 Sprint Planning or Client Briefing"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    autoFocus
                  />
                </div>

                <div className="form-group">
                  <label>Description (Optional)</label>
                  <textarea
                    placeholder="Context, agenda, or attendees..."
                    rows={3}
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Meeting Platform</label>
                    <select
                      value={meetingMode === "offline" ? "in_person" : platform}
                      onChange={(e) => setPlatform(e.target.value)}
                      disabled={meetingMode === "offline"}
                    >
                      <option value="google_meet">Google Meet</option>
                      <option value="zoom">Zoom</option>
                      <option value="teams">Microsoft Teams</option>
                      <option value="custom">Other / Browser Call</option>
                      <option value="in_person">In-person meeting</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Spoken Language</label>
                    <select
                      value={sourceLang}
                      onChange={(e) => setSourceLang(e.target.value)}
                    >
                      <option value="auto">Auto-Detect</option>
                      <option value="en">English</option>
                      <option value="hi">Hindi (हिंदी)</option>
                      <option value="pa">Punjabi (ਪੰਜਾਬੀ)</option>
                      <option value="mr">Marathi (मराठी)</option>
                      <option value="gu">Gujarati (ગુજરાતી)</option>
                      <option value="bn">Bengali (বাংলা)</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Intelligence / Translation Target</label>
                    <select
                      value={targetLang}
                      onChange={(e) => setTargetLang(e.target.value)}
                    >
                      <option value="en">English (Default)</option>
                      <option value="hi">Hindi</option>
                      <option value="es">Spanish</option>
                      <option value="fr">French</option>
                      <option value="de">German</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  onClick={() => handleCreate("upload")}
                  disabled={creating}
                  className="btn-modal-secondary"
                >
                  <Upload size={16} /> Create & Upload Audio
                </button>
                <button
                  type="button"
                  onClick={() => handleCreate("record")}
                  disabled={creating}
                  className="btn-modal-primary"
                >
                  <Mic size={16} /> {creating ? "Creating..." : "Start Live Recording"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function MeetingsDashboard() {
  return (
    <Suspense
      fallback={
        <div className="actionmic-page">
          <Navbar />
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading meeting intelligence records...</p>
          </div>
        </div>
      }
    >
      <MeetingsDashboardContent />
    </Suspense>
  );
}
