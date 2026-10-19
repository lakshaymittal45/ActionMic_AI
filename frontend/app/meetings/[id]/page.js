"use client";

import { useState, useEffect, useRef, use } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  getMeeting,
  updateMeeting,
  getMeetingTranscript,
  getMeetingIntelligence,
  regenerateIntelligence,
  updateSpeakerName,
  createActionItem,
  updateActionItem,
  deleteActionItem,
  getMeetingAudioStreamUrl,
  getMeetingExportUrl,
  triggerMeetingProcessing,
  uploadMeetingAudio
} from "@/lib/api";
import {
  Play,
  Pause,
  RotateCcw,
  Volume2,
  Calendar,
  Clock,
  Sparkles,
  CheckCircle2,
  Circle,
  AlertCircle,
  FileText,
  Download,
  Users,
  Languages,
  Mic,
  Upload,
  RefreshCw,
  Plus,
  Trash2,
  Edit2,
  Check,
  X,
  ExternalLink,
  Share2,
  ChevronLeft,
  ArrowRight
} from "lucide-react";

export default function MeetingWorkspace({ params }) {
  // Unwrap params using React 19 use()
  const resolvedParams = use(params);
  const meetingId = resolvedParams.id;

  const [meeting, setMeeting] = useState(null);
  const [segments, setSegments] = useState([]);
  const [intelligence, setIntelligence] = useState(null);
  const [activeTab, setActiveTab] = useState("intelligence"); // intelligence, transcript, speakers, export
  const [transcriptView, setTranscriptView] = useState("original"); // original, translation, transliteration
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Audio Player State
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1.0);

  // Speaker Renaming State
  const [editingSpeakerId, setEditingSpeakerId] = useState(null);
  const [speakerDisplayName, setSpeakerDisplayName] = useState("");

  // Action Item Creation Modal
  const [showActionModal, setShowActionModal] = useState(false);
  const [actionTitle, setActionTitle] = useState("");
  const [actionAssignee, setActionAssignee] = useState("");
  const [actionPriority, setActionPriority] = useState("medium");
  const [actionDue, setActionDue] = useState("");

  // File Upload State
  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);
  const [editedTitle, setEditedTitle] = useState("");
  const [editedDescription, setEditedDescription] = useState("");
  const [linkCopied, setLinkCopied] = useState(false);

  useEffect(() => {
    loadAllData();
  }, [meetingId]);

  // Keep the workspace current while background transcription is running.
  useEffect(() => {
    if (!meeting || !["pending", "processing", "queued"].includes(meeting.processing_status)) return;
    const poll = setInterval(async () => {
      try {
        const nextMeeting = await getMeeting(meetingId);
        setMeeting(nextMeeting);
        if (!["pending", "processing", "queued"].includes(nextMeeting.processing_status)) {
          await loadAllData();
        }
      } catch (err) {
        console.warn("Meeting status refresh failed", err);
      }
    }, 10000);
    return () => clearInterval(poll);
  }, [meetingId, meeting?.processing_status]);

  async function loadAllData() {
    try {
      setLoading(true);
      const [meetingData, transcriptData, intelData] = await Promise.all([
        getMeeting(meetingId),
        getMeetingTranscript(meetingId).catch(() => []),
        getMeetingIntelligence(meetingId).catch(() => null)
      ]);

      setMeeting(meetingData);
      setSegments(transcriptData || []);
      setIntelligence(intelData);
    } catch (err) {
      console.error("Error loading workspace data:", err);
    } finally {
      setLoading(false);
    }
  }

  // Audio seek helper
  function seekTo(seconds) {
    if (audioRef.current) {
      audioRef.current.currentTime = seconds;
      audioRef.current.play();
      setIsPlaying(true);
    }
  }

  function togglePlay() {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  }

  function handlePlaybackRate(rate) {
    setPlaybackRate(rate);
    if (audioRef.current) {
      audioRef.current.playbackRate = rate;
    }
  }

  // Action item toggle
  async function toggleActionItem(item) {
    const newStatus = item.status === "completed" ? "pending" : "completed";
    try {
      const updated = await updateActionItem(meetingId, item.id, { status: newStatus });
      setIntelligence((prev) => ({
        ...prev,
        action_items: prev.action_items.map((ai) => (ai.id === item.id ? updated : ai))
      }));
    } catch (err) {
      alert("Failed to update action item: " + err.message);
    }
  }

  async function handleAddActionItem(e) {
    e.preventDefault();
    if (!actionTitle.trim()) return;
    try {
      const newItem = await createActionItem(meetingId, {
        title: actionTitle.trim(),
        assignee_name: actionAssignee.trim() || null,
        priority: actionPriority,
        due_at: actionDue || null
      });

      setIntelligence((prev) => ({
        ...prev,
        action_items: [newItem, ...(prev.action_items || [])]
      }));

      setShowActionModal(false);
      setActionTitle("");
      setActionAssignee("");
      setActionDue("");
    } catch (err) {
      alert("Failed to create action item: " + err.message);
    }
  }

  async function handleDeleteAction(itemId) {
    try {
      await deleteActionItem(meetingId, itemId);
      setIntelligence((prev) => ({
        ...prev,
        action_items: prev.action_items.filter((ai) => ai.id !== itemId)
      }));
    } catch (err) {
      alert("Failed to delete action item: " + err.message);
    }
  }

  // Speaker name update
  async function handleSpeakerRename(speakerId) {
    if (!speakerDisplayName.trim()) return;
    try {
      await updateSpeakerName(meetingId, speakerId, speakerDisplayName.trim());
      setEditingSpeakerId(null);
      // Reload segments to reflect new name
      const tr = await getMeetingTranscript(meetingId);
      setSegments(tr);
      const m = await getMeeting(meetingId);
      setMeeting(m);
    } catch (err) {
      alert("Failed to update speaker name: " + err.message);
    }
  }

  // Regenerate intelligence
  async function handleRegenerate() {
    try {
      setRefreshing(true);
      await regenerateIntelligence(meetingId);
      setTimeout(async () => {
        const intel = await getMeetingIntelligence(meetingId);
        setIntelligence(intel);
        setRefreshing(false);
      }, 3000);
    } catch (err) {
      setRefreshing(false);
      alert("Failed to re-trigger intelligence: " + err.message);
    }
  }

  async function handleRetryProcessing() {
    try {
      setRefreshing(true);
      await triggerMeetingProcessing(meetingId);
      setMeeting((current) => ({ ...current, processing_status: "pending" }));
    } catch (err) {
      alert("Failed to retry processing: " + err.message);
    } finally {
      setRefreshing(false);
    }
  }

  // Upload Audio
  async function handleAudioUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = /\.(wav|mp3|m4a|flac|webm|ogg|mp4|mov|avi|mkv|m4v)$/i;
    if (!allowed.test(file.name)) {
      alert("Please choose an audio or video recording file.");
      e.target.value = "";
      return;
    }
    if (file.size > 2 * 1024 * 1024 * 1024) {
      alert("The recording must be smaller than 2 GB.");
      e.target.value = "";
      return;
    }
    try {
      setUploading(true);
      await uploadMeetingAudio(meetingId, file);
      alert("Audio uploaded! Processing has begun in the background.");
      loadAllData();
    } catch (err) {
      alert("Upload failed: " + err.message);
    } finally {
      setUploading(false);
    }
  }

  function beginEditingDetails() {
    setEditedTitle(meeting.title || "");
    setEditedDescription(meeting.description || "");
    setEditingDetails(true);
  }

  async function saveMeetingDetails() {
    if (!editedTitle.trim()) return;
    try {
      const updated = await updateMeeting(meetingId, {
        title: editedTitle.trim(),
        description: editedDescription.trim() || null
      });
      setMeeting((current) => ({ ...current, ...updated }));
      setEditingDetails(false);
    } catch (err) {
      alert("Failed to save meeting details: " + err.message);
    }
  }

  async function copyMeetingLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch {
      alert("Unable to copy the meeting link");
    }
  }

  if (loading) {
    return (
      <div className="actionmic-page">
        <Navbar />
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading meeting intelligence workspace...</p>
        </div>
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="actionmic-page">
        <Navbar />
        <div className="actionmic-container">
          <div className="empty-state-card">
            <h3>Meeting not found</h3>
            <Link href="/meetings" className="btn-primary-glow">Return to Dashboard</Link>
          </div>
        </div>
      </div>
    );
  }

  // Filter segments by search
  const filteredSegments = segments.filter((s) => {
    if (!searchQuery) return true;
    const text = s.original_text?.toLowerCase() || "";
    const spk = s.speaker_name?.toLowerCase() || s.speaker_label?.toLowerCase() || "";
    return text.includes(searchQuery.toLowerCase()) || spk.includes(searchQuery.toLowerCase());
  });

  const audioStreamUrl = getMeetingAudioStreamUrl(meetingId);
  const hasAudio = !!meeting.audio_storage_key;
  const isProcessing = ["pending", "processing", "queued"].includes(meeting.processing_status);

  return (
    <div className="actionmic-page">
      <Navbar />

      <main className="actionmic-container workspace-container">
        {/* Back Link & Header */}
        <div className="workspace-header">
          <div className="workspace-header-top">
            <Link href="/meetings" className="back-link">
              <ChevronLeft size={16} /> Back to Meetings
            </Link>
            <div className="workspace-badges">
              <span className={`status-pill ${meeting.recording_status === "recording" ? "recording" : meeting.processing_status}`}>
                {meeting.recording_status === "recording" ? "● Recording Live" : meeting.processing_status || meeting.status}
              </span>
              <span className="lang-tag">
                {meeting.source_language?.toUpperCase() || "AUTO"} → {meeting.target_language?.toUpperCase() || "EN"}
              </span>
            </div>
          </div>

          <div className="workspace-title-row">
            <div className="workspace-title-editor">
              {editingDetails ? (
                <div className="meeting-details-form">
                  <input value={editedTitle} onChange={(e) => setEditedTitle(e.target.value)} className="workspace-title-input" autoFocus />
                  <textarea value={editedDescription} onChange={(e) => setEditedDescription(e.target.value)} placeholder="Add a description or agenda" rows={2} className="workspace-desc-input" />
                  <div className="inline-form-actions">
                    <button onClick={saveMeetingDetails} className="btn-primary-glow" disabled={!editedTitle.trim()}><Check size={15} /> Save</button>
                    <button onClick={() => setEditingDetails(false)} className="btn-secondary-glow"><X size={15} /> Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="workspace-title-with-edit">
                    <h1 className="workspace-title">{meeting.title}</h1>
                    <button onClick={beginEditingDetails} className="icon-action-btn" title="Edit meeting details"><Edit2 size={15} /></button>
                  </div>
                  {meeting.description && <p className="workspace-desc">{meeting.description}</p>}
                </>
              )}
            </div>

            <div className="workspace-header-actions">
              {meeting.recording_status === "recording" ? (
                <Link href={`/meetings/${meetingId}/record`} className="btn-record-pulse">
                  <Mic size={16} /> Return to Live Session
                </Link>
              ) : (
                <Link href={`/meetings/${meetingId}/record`} className="btn-secondary-glow">
                  <Mic size={16} /> Record Session
                </Link>
              )}

              <input
                type="file"
                ref={fileInputRef}
                onChange={handleAudioUpload}
                accept="audio/*,video/*,.wav,.mp3,.m4a,.flac,.webm,.ogg,.mp4,.mov,.avi,.mkv,.m4v"
                style={{ display: "none" }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="btn-secondary-glow"
                title="Upload or replace audio or video"
              >
                <Upload size={16} /> {uploading ? "Uploading..." : "Upload Media"}
              </button>

              <button
                onClick={meeting.processing_status === "failed" ? handleRetryProcessing : handleRegenerate}
                disabled={refreshing}
                className="btn-primary-glow"
              >
                {meeting.processing_status === "failed" ? <RefreshCw size={16} className={refreshing ? "spin-icon" : ""} /> : <Sparkles size={16} className={refreshing ? "spin-icon" : ""} />}
                <span>{refreshing ? "Processing..." : meeting.processing_status === "failed" ? "Retry Processing" : "Re-Run Intelligence"}</span>
              </button>
              <button onClick={copyMeetingLink} className="btn-secondary-glow" title="Copy meeting link">
                <Share2 size={16} /> {linkCopied ? "Link Copied" : "Share"}
              </button>
              {hasAudio && (
                <button onClick={handleRetryProcessing} disabled={refreshing || isProcessing} className="btn-secondary-glow" title="Run the full audio pipeline again">
                  <RefreshCw size={16} className={refreshing ? "spin-icon" : ""} /> Reprocess Audio
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Audio Player Bar */}
        {hasAudio && (
          <div className="audio-player-bar">
            <audio
              ref={audioRef}
              src={audioStreamUrl}
              onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime || 0)}
              onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
              onEnded={() => setIsPlaying(false)}
            />

            <button onClick={togglePlay} className="audio-play-btn">
              {isPlaying ? <Pause size={20} /> : <Play size={20} className="play-icon-offset" />}
            </button>

            <div className="audio-scrubber-group">
              <span className="time-display">{formatSeconds(currentTime)}</span>
              <input
                type="range"
                min="0"
                max={duration || 100}
                value={currentTime}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setCurrentTime(val);
                  if (audioRef.current) audioRef.current.currentTime = val;
                }}
                className="audio-scrubber"
              />
              <span className="time-display">{formatSeconds(duration)}</span>
            </div>

            <div className="speed-selector">
              {[1.0, 1.25, 1.5, 2.0].map((rate) => (
                <button
                  key={rate}
                  onClick={() => handlePlaybackRate(rate)}
                  className={`speed-pill ${playbackRate === rate ? "active" : ""}`}
                >
                  {rate}x
                </button>
              ))}
            </div>
          </div>
        )}

        {isProcessing && (
          <div className="processing-notice">
            <div className="processing-notice-icon"><RefreshCw size={20} className="spin-icon" /></div>
            <div>
              <strong>Meeting is still being processed</strong>
              <p>Get back shortly for transcript details, summary, decisions, and action items.</p>
            </div>
            <span className="processing-notice-status">{meeting.processing_status}</span>
          </div>
        )}

        {/* Workspace Tab Bar */}
        <div className="workspace-tabs-bar">
          <button
            onClick={() => setActiveTab("intelligence")}
            className={`tab-btn ${activeTab === "intelligence" ? "active" : ""}`}
          >
            <Sparkles size={16} />
            <span>Meeting Intelligence</span>
            {intelligence?.action_items?.length > 0 && (
              <span className="tab-counter">{intelligence.action_items.length}</span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("transcript")}
            className={`tab-btn ${activeTab === "transcript" ? "active" : ""}`}
          >
            <FileText size={16} />
            <span>Transcript & Translations</span>
            {segments.length > 0 && <span className="tab-counter">{segments.length}</span>}
          </button>

          <button
            onClick={() => setActiveTab("speakers")}
            className={`tab-btn ${activeTab === "speakers" ? "active" : ""}`}
          >
            <Users size={16} />
            <span>Speakers</span>
          </button>

          <button
            onClick={() => setActiveTab("export")}
            className={`tab-btn ${activeTab === "export" ? "active" : ""}`}
          >
            <Download size={16} />
            <span>Export & Share</span>
          </button>
        </div>

        {/* TAB 1: INTELLIGENCE */}
        {activeTab === "intelligence" && (
          <div className="tab-pane intelligence-pane">
            {/* Executive Summary Card */}
            <div className="intelligence-card summary-card">
              <div className="card-header">
                <div className="header-title-wrap">
                  <Sparkles size={18} className="sparkle-icon" />
                  <h3>Executive Summary</h3>
                </div>
                {intelligence?.summary?.model_name && (
                  <span className="model-badge">AI Engine: {intelligence.summary.model_name}</span>
                )}
              </div>
              <div className="card-body">
                <p className="summary-text">
                  {intelligence?.summary?.content || (isProcessing
                    ? "Your meeting summary will appear here when processing is complete."
                    : "No summary generated yet. Record conversation or click Re-Run Intelligence.")}
                </p>

                {/* Key Takeaways */}
                {intelligence?.summary?.structured_content_json?.key_takeaways?.length > 0 && (
                  <div className="takeaways-box">
                    <h4>Key Takeaways</h4>
                    <ul className="takeaways-list">
                      {intelligence.summary.structured_content_json.key_takeaways.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Topics Covered */}
                {intelligence?.summary?.structured_content_json?.topics_covered?.length > 0 && (
                  <div className="topics-wrap">
                    <h4>Topics Covered:</h4>
                    <div className="topics-chips">
                      {intelligence.summary.structured_content_json.topics_covered.map((t, idx) => (
                        <span key={idx} className="topic-chip">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="intelligence-columns">
              {/* Left Column: Action Items */}
              <div className="intelligence-card actions-card">
                <div className="card-header">
                  <div className="header-title-wrap">
                    <CheckCircle2 size={18} className="emerald-icon" />
                    <h3>Action Items & Tasks</h3>
                  </div>
                  <button onClick={() => setShowActionModal(true)} className="btn-add-action">
                    <Plus size={14} /> Add Task
                  </button>
                </div>

                <div className="card-body">
                  {!intelligence?.action_items || intelligence.action_items.length === 0 ? (
                    <div className="empty-substate">
                      <p>No action items extracted.</p>
                    </div>
                  ) : (
                    <div className="action-items-list">
                      {intelligence.action_items.map((item) => (
                        <div key={item.id} className={`action-item-row ${item.status}`}>
                          <button onClick={() => toggleActionItem(item)} className="checkbox-btn">
                            {item.status === "completed" ? (
                              <CheckCircle2 size={20} className="checked-icon" />
                            ) : (
                              <Circle size={20} className="unchecked-icon" />
                            )}
                          </button>

                          <div className="action-content">
                            <span className={`action-title ${item.status === "completed" ? "completed-text" : ""}`}>
                              {item.title}
                            </span>
                            <div className="action-meta">
                              {item.assignee_name && (
                                <span className="assignee-tag">👤 {item.assignee_name}</span>
                              )}
                              {item.due_at && (
                                <span className="due-tag">📅 {new Date(item.due_at).toLocaleDateString()}</span>
                              )}
                              <span className={`priority-tag ${item.priority}`}>
                                {item.priority?.toUpperCase()}
                              </span>
                            </div>
                          </div>

                          <button
                            onClick={() => handleDeleteAction(item.id)}
                            className="delete-item-btn"
                            title="Delete task"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Decisions & Key Points */}
              <div className="intelligence-column-right">
                {/* Decisions */}
                <div className="intelligence-card decisions-card">
                  <div className="card-header">
                    <div className="header-title-wrap">
                      <Check size={18} className="blue-icon" />
                      <h3>Decisions & Agreements</h3>
                    </div>
                  </div>
                  <div className="card-body">
                    {!intelligence?.decisions || intelligence.decisions.length === 0 ? (
                      <div className="empty-substate">
                        <p>No decisions captured.</p>
                      </div>
                    ) : (
                      <div className="decisions-list">
                        {intelligence.decisions.map((dec) => (
                          <div key={dec.id} className="decision-item">
                            <div className="decision-header">
                              <span className="decision-text">{dec.description}</span>
                              <span className={`decision-status-pill ${dec.decision_status}`}>
                                {dec.decision_status?.replace("_", " ")}
                              </span>
                            </div>
                            {dec.rationale && (
                              <p className="decision-rationale">Rationale: {dec.rationale}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Key Discussion Points */}
                <div className="intelligence-card keypoints-card">
                  <div className="card-header">
                    <div className="header-title-wrap">
                      <FileText size={18} className="amber-icon" />
                      <h3>Key Discussion Points</h3>
                    </div>
                  </div>
                  <div className="card-body">
                    {!intelligence?.key_points || intelligence.key_points.length === 0 ? (
                      <div className="empty-substate">
                        <p>No key discussion points recorded.</p>
                      </div>
                    ) : (
                      <div className="keypoints-list">
                        {intelligence.key_points.map((kp) => (
                          <div key={kp.id} className="keypoint-item">
                            <div className="keypoint-title-row">
                              <span className="keypoint-title">{kp.title}</span>
                              <span className="keypoint-category">{kp.category || "General"}</span>
                            </div>
                            {kp.description && kp.description !== kp.title && (
                              <p className="keypoint-desc">{kp.description}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: TRANSCRIPT */}
        {activeTab === "transcript" && (
          <div className="tab-pane transcript-pane">
            {/* View Switcher and Search */}
            <div className="transcript-toolbar">
              <div className="view-selector">
                <button
                  onClick={() => setTranscriptView("original")}
                  className={`view-pill ${transcriptView === "original" ? "active" : ""}`}
                >
                  Original Speech
                </button>
                <button
                  onClick={() => setTranscriptView("translation")}
                  className={`view-pill ${transcriptView === "translation" ? "active" : ""}`}
                >
                  English Translation
                </button>
                <button
                  onClick={() => setTranscriptView("transliteration")}
                  className={`view-pill ${transcriptView === "transliteration" ? "active" : ""}`}
                >
                  Romanized (Transliterated)
                </button>
              </div>

              <div className="transcript-search">
                <input
                  type="text"
                  placeholder="Search in transcript..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>

            {/* Transcript Bubbles */}
            {filteredSegments.length === 0 ? (
              <div className="empty-state-card">
                <p>No transcript segments found.</p>
              </div>
            ) : (
              <div className="transcript-stream">
                {filteredSegments.map((seg) => {
                  const startTimeSec = (seg.start_time_ms || 0) / 1000;
                  const translationVariant = seg.variants?.find((v) => v.variant_type === "translation");
                  const transliterationVariant = seg.variants?.find((v) => v.variant_type === "transliteration");

                  let displayedText = seg.original_text;
                  if (transcriptView === "translation" && translationVariant) {
                    displayedText = translationVariant.text;
                  } else if (transcriptView === "transliteration" && transliterationVariant) {
                    displayedText = transliterationVariant.text;
                  }

                  return (
                    <div key={seg.id} className="transcript-bubble">
                      <div className="bubble-header">
                        <div className="speaker-tag">
                          {editingSpeakerId === seg.speaker_id ? (
                            <div className="inline-rename">
                              <input
                                type="text"
                                value={speakerDisplayName}
                                onChange={(e) => setSpeakerDisplayName(e.target.value)}
                                autoFocus
                              />
                              <button onClick={() => handleSpeakerRename(seg.speaker_id)} className="save-btn">✓</button>
                              <button onClick={() => setEditingSpeakerId(null)} className="cancel-btn">×</button>
                            </div>
                          ) : (
                            <button
                              onClick={() => {
                                setEditingSpeakerId(seg.speaker_id);
                                setSpeakerDisplayName(seg.speaker_name || seg.speaker_label);
                              }}
                              className="speaker-name-btn"
                              title="Click to rename speaker"
                            >
                              <span>{seg.speaker_name || seg.speaker_label}</span>
                              <Edit2 size={12} className="edit-icon" />
                            </button>
                          )}
                        </div>

                        <button
                          onClick={() => seekTo(startTimeSec)}
                          className="timestamp-pill"
                          title="Seek audio to this segment"
                        >
                          <Play size={10} />
                          <span>{formatMs(seg.start_time_ms)}</span>
                        </button>
                      </div>

                      <div className="bubble-content">
                        <p>{displayedText}</p>

                        {/* Alternate variant hints if viewing original */}
                        {transcriptView === "original" && translationVariant && (
                          <div className="variant-hint translation">
                            <span className="hint-label">Translation:</span> {translationVariant.text}
                          </div>
                        )}
                        {transcriptView === "original" && transliterationVariant && (
                          <div className="variant-hint transliteration">
                            <span className="hint-label">Romanized:</span> {transliterationVariant.text}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: SPEAKERS */}
        {activeTab === "speakers" && (
          <div className="tab-pane speakers-pane">
            <div className="speakers-grid">
              {(meeting.speakers || []).map((spk) => (
                <div key={spk.id} className="speaker-card">
                  <div className="speaker-avatar">
                    <Users size={24} />
                  </div>
                  <div className="speaker-card-info">
                    {editingSpeakerId === spk.id ? (
                      <div className="inline-rename">
                        <input
                          type="text"
                          value={speakerDisplayName}
                          onChange={(e) => setSpeakerDisplayName(e.target.value)}
                          autoFocus
                        />
                        <button onClick={() => handleSpeakerRename(spk.id)} className="save-btn">Save</button>
                        <button onClick={() => setEditingSpeakerId(null)} className="cancel-btn">Cancel</button>
                      </div>
                    ) : (
                      <>
                        <h4 className="speaker-card-name">{spk.display_name}</h4>
                        <span className="speaker-card-label">Label: {spk.speaker_label}</span>
                        <button
                          onClick={() => {
                            setEditingSpeakerId(spk.id);
                            setSpeakerDisplayName(spk.display_name);
                          }}
                          className="btn-rename-pill"
                        >
                          <Edit2 size={12} /> Rename
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 4: EXPORT */}
        {activeTab === "export" && (
          <div className="tab-pane export-pane">
            <div className="export-cards-grid">
              <a
                href={getMeetingExportUrl(meetingId, "markdown")}
                target="_blank"
                rel="noreferrer"
                className="export-card"
              >
                <div className="export-icon bg-blue">
                  <FileText size={24} />
                </div>
                <div className="export-text">
                  <h4>Markdown Document (.md)</h4>
                  <p>Formatted meeting notes with headings, speaker dialogue, and translation quotes.</p>
                </div>
                <Download size={18} className="dl-icon" />
              </a>

              <a
                href={getMeetingExportUrl(meetingId, "txt")}
                target="_blank"
                rel="noreferrer"
                className="export-card"
              >
                <div className="export-icon bg-emerald">
                  <FileText size={24} />
                </div>
                <div className="export-text">
                  <h4>Plain Text (.txt)</h4>
                  <p>Lightweight speaker-tagged transcript with millisecond timestamps.</p>
                </div>
                <Download size={18} className="dl-icon" />
              </a>

              <a
                href={getMeetingExportUrl(meetingId, "srt")}
                target="_blank"
                rel="noreferrer"
                className="export-card"
              >
                <div className="export-icon bg-purple">
                  <Clock size={24} />
                </div>
                <div className="export-text">
                  <h4>SubRip Subtitles (.srt)</h4>
                  <p>Standard subtitle file with millisecond sync for media players.</p>
                </div>
                <Download size={18} className="dl-icon" />
              </a>

              <a
                href={getMeetingExportUrl(meetingId, "vtt")}
                target="_blank"
                rel="noreferrer"
                className="export-card"
              >
                <div className="export-icon bg-amber">
                  <Languages size={24} />
                </div>
                <div className="export-text">
                  <h4>WebVTT Subtitles (.vtt)</h4>
                  <p>Web video subtitle standard with speaker voice tagging.</p>
                </div>
                <Download size={18} className="dl-icon" />
              </a>

              <a
                href={getMeetingExportUrl(meetingId, "json")}
                target="_blank"
                rel="noreferrer"
                className="export-card"
              >
                <div className="export-icon bg-slate">
                  <ExternalLink size={24} />
                </div>
                <div className="export-text">
                  <h4>Raw JSON (.json)</h4>
                  <p>Full structured data including segments, variants, and metadata.</p>
                </div>
                <Download size={18} className="dl-icon" />
              </a>

              {hasAudio && (
                <a
                  href={`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/meetings/${meetingId}/audio/download`}
                  target="_blank"
                  rel="noreferrer"
                  className="export-card"
                >
                  <div className="export-icon bg-red">
                    <Volume2 size={24} />
                  </div>
                  <div className="export-text">
                    <h4>Master Audio Recording (.wav)</h4>
                    <p>Original high-quality audio file for archiving or external playback.</p>
                  </div>
                  <Download size={18} className="dl-icon" />
                </a>
              )}
            </div>
          </div>
        )}

        {/* Add Action Item Modal */}
        {showActionModal && (
          <div className="modal-backdrop" onClick={() => setShowActionModal(false)}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2>Add Action Item</h2>
                <button onClick={() => setShowActionModal(false)} className="close-btn">×</button>
              </div>

              <form onSubmit={handleAddActionItem}>
                <div className="modal-body">
                  <div className="form-group">
                    <label>Task Title *</label>
                    <input
                      type="text"
                      placeholder="e.g. Deploy production release or follow up with vendor"
                      value={actionTitle}
                      onChange={(e) => setActionTitle(e.target.value)}
                      autoFocus
                      required
                    />
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Assignee Name</label>
                      <input
                        type="text"
                        placeholder="e.g. Sarah Jenkins"
                        value={actionAssignee}
                        onChange={(e) => setActionAssignee(e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label>Priority</label>
                      <select
                        value={actionPriority}
                        onChange={(e) => setActionPriority(e.target.value)}
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="critical">Critical</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Due Date</label>
                    <input
                      type="date"
                      value={actionDue}
                      onChange={(e) => setActionDue(e.target.value)}
                    />
                  </div>
                </div>

                <div className="modal-footer">
                  <button
                    type="button"
                    onClick={() => setShowActionModal(false)}
                    className="btn-modal-secondary"
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn-modal-primary">
                    Save Action Item
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function formatSeconds(secs) {
  if (!secs || isNaN(secs)) return "00:00";
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function formatMs(ms) {
  if (!ms || isNaN(ms)) return "00:00";
  const totalSeconds = Math.floor(ms / 1000);
  return formatSeconds(totalSeconds);
}
