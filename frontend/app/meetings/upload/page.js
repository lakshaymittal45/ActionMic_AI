"use client";

import { useState, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { createMeeting, uploadMeetingAudio } from "@/lib/api";
import {
  Upload,
  FileAudio,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  Sparkles,
  Languages
} from "lucide-react";

function audioBufferToWav(audioBuffer) {
  const channelCount = audioBuffer.numberOfChannels;
  const frameCount = audioBuffer.length;
  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const buffer = new ArrayBuffer(44 + frameCount * blockAlign);
  const view = new DataView(buffer);

  function writeString(offset, value) {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + frameCount * blockAlign, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, frameCount * blockAlign, true);

  const channels = Array.from({ length: channelCount }, (_, channel) => audioBuffer.getChannelData(channel));
  let offset = 44;
  for (let frame = 0; frame < frameCount; frame += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      const sample = Math.max(-1, Math.min(1, channels[channel][frame]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += bytesPerSample;
    }
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function UploadMeetingAudioContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isVideo = searchParams.get("mode") === "video";
  const fileInputRef = useRef(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("en");
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progressStatus, setProgressStatus] = useState("");
  const [errorMessage, setErrorMessage] = useState(null);

  function handleFileDrop(e) {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
      if (!title) {
        setTitle(file.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
    }
  }

  function handleFileSelect(e) {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      if (!title) {
        setTitle(file.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMessage(`Please select a ${isVideo ? "video" : "audio"} file to upload`);
      return;
    }
    const allowed = isVideo
      ? /\.(mp4|mov|avi|mkv|webm|m4v)$/i
      : /\.(wav|mp3|m4a|flac|webm|ogg)$/i;
    if (!allowed.test(selectedFile.name)) {
      setErrorMessage(`Please select a supported ${isVideo ? "video" : "audio"} format`);
      return;
    }
    if (selectedFile.size > 2 * 1024 * 1024 * 1024) {
      setErrorMessage("The recording must be smaller than 2 GB");
      return;
    }
    if (!title.trim()) {
      setErrorMessage("Please enter a meeting title");
      return;
    }

    try {
      setUploading(true);
      setErrorMessage(null);
      setProgressStatus("Creating meeting record in database...");

      // 1. Create meeting
      const meeting = await createMeeting({
        title: title.trim(),
        description: description.trim() || null,
        source_type: "upload",
        source_language: sourceLang,
        target_language: targetLang
      });

      // 2. Convert video locally when needed, then reuse the audio pipeline.
      let audioFile = selectedFile;
      if (isVideo) {
        setProgressStatus("Extracting audio from video in your browser...");
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        const audioContext = new AudioContextClass();
        try {
          const audioBuffer = await audioContext.decodeAudioData(await selectedFile.arrayBuffer());
          const wavBlob = audioBufferToWav(audioBuffer);
          audioFile = new File([
            wavBlob
          ], `${selectedFile.name.replace(/\.[^/.]+$/, "")}.wav`, { type: "audio/wav" });
        } finally {
          await audioContext.close();
        }
      }

      setProgressStatus("Uploading audio and starting intelligence pipeline...");
      await uploadMeetingAudio(meeting.id, audioFile);

      setProgressStatus("Complete! Redirecting to workspace...");
      setTimeout(() => {
        router.push(`/meetings/${meeting.id}`);
      }, 800);
    } catch (err) {
      setErrorMessage(err.message || "Failed to upload audio");
      setUploading(false);
    }
  }

  return (
    <div className="actionmic-page">
      <Navbar />

      <main className="actionmic-container upload-container">
        <div className="upload-header">
          <Link href="/meetings" className="back-link">
            <ArrowLeft size={16} /> Back to Meetings
          </Link>
            <h1 className="page-heading">{isVideo ? "Convert Video to Audio" : "Upload Audio & Process"}</h1>
          <p className="page-subheading">
            {isVideo
              ? "Upload a meeting video. We’ll extract its audio and start transcription and meeting intelligence."
              : "Upload pre-recorded audio from Zoom, Google Meet, Teams, phone calls, or voice notes. Supports multilingual Indic speech, automatic diarization, and action item extraction."}
          </p>
        </div>

        {errorMessage && <div className="modal-error mb-4">{errorMessage}</div>}

        <form onSubmit={handleSubmit} className="upload-form">
          {/* Drag & Drop Box */}
          <div
            className={`dropzone-card ${selectedFile ? "has-file" : ""}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept={isVideo ? "video/*,.mp4,.mov,.avi,.mkv,.webm" : "audio/*,.wav,.mp3,.m4a,.flac,.webm,.ogg"}
              style={{ display: "none" }}
            />

            <div className="dropzone-content">
              {selectedFile ? (
                <>
                  <div className="file-icon-wrapper bg-emerald">
                    <CheckCircle2 size={32} />
                  </div>
                  <h3>{selectedFile.name}</h3>
                  <p className="file-size">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</p>
                  <span className="change-file-btn">Click to change file</span>
                </>
              ) : (
                <>
                  <div className="file-icon-wrapper bg-blue">
                    <Upload size={32} />
                  </div>
                  <h3>Drag & drop meeting {isVideo ? "video" : "audio"} here</h3>
                  <p>or click to browse from your computer</p>
                  <span className="file-formats-tag">Supports {isVideo ? "MP4, MOV, AVI, MKV, WebM" : "WAV, MP3, M4A, FLAC, WebM, OGG"}</span>
                </>
              )}
            </div>
          </div>

          {/* Meeting Metadata */}
          <div className="form-card">
            <div className="form-group">
              <label>Meeting Title *</label>
              <input
                type="text"
                placeholder="e.g. Executive Board Meeting - Q3 Review"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label>Description / Agenda (Optional)</label>
              <textarea
                placeholder="Provide context, key topics, or participant list..."
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Spoken Language</label>
                <select
                  value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}
                >
                  <option value="auto">Auto-Detect Language</option>
                  <option value="en">English</option>
                  <option value="hi">Hindi (हिंदी)</option>
                  <option value="pa">Punjabi (ਪੰਜਾਬੀ)</option>
                  <option value="mr">Marathi (मराठी)</option>
                  <option value="gu">Gujarati (ગુજરાતી)</option>
                  <option value="bn">Bengali (বাংলা)</option>
                </select>
              </div>

              <div className="form-group">
                <label>Target Translation Language</label>
                <select
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                >
                  <option value="en">English (Default)</option>
                  <option value="hi">Hindi</option>
                  <option value="es">Spanish</option>
                  <option value="fr">French</option>
                </select>
              </div>
            </div>

            {uploading && (
              <div className="upload-progress-box">
                <div className="spinner"></div>
                <p>{progressStatus}</p>
              </div>
            )}

            <div className="form-actions">
              <button
                type="submit"
                disabled={uploading || !selectedFile}
                className="btn-upload-submit"
              >
                <Sparkles size={18} />
                <span>{uploading ? "Processing..." : isVideo ? "Convert & Analyze Meeting" : "Upload & Analyze Meeting"}</span>
              </button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}

export default function UploadMeetingAudioPage() {
  return (
    <Suspense fallback={<div className="loading-state"><div className="spinner" /></div>}>
      <UploadMeetingAudioContent />
    </Suspense>
  );
}
