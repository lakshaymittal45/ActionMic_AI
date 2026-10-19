"use client";

import { useState, useEffect, useRef, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import {
  getMeeting,
  startMeetingRecording,
  stopMeetingRecording
} from "@/lib/api";
import {
  Mic,
  MicOff,
  Pause,
  Play,
  Square,
  Sparkles,
  ArrowLeft,
  ShieldCheck,
  Radio,
  FileText,
  Volume2
} from "lucide-react";

export default function LiveMeetingRoom({ params }) {
  const resolvedParams = use(params);
  const meetingId = resolvedParams.id;
  const router = useRouter();

  const [meeting, setMeeting] = useState(null);
  const [recordingState, setRecordingState] = useState("idle"); // idle, recording, paused, stopping
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [savedChunksCount, setSavedChunksCount] = useState(0);
  const [interimTranscripts, setInterimTranscripts] = useState([]);
  const [errorMessage, setErrorMessage] = useState(null);
  const recordingStateRef = useRef("idle");
  const lastTranscriptRef = useRef("");

  // Audio / WebSocket refs
  const audioContextRef = useRef(null);
  const streamRef = useRef(null);
  const displayStreamRef = useRef(null);
  const processorRef = useRef(null);
  const socketRef = useRef(null);
  const canvasRef = useRef(null);
  const timerRef = useRef(null);
  const animFrameRef = useRef(null);

  function updateRecordingState(nextState) {
    recordingStateRef.current = nextState;
    setRecordingState(nextState);
  }

  useEffect(() => {
    getMeeting(meetingId)
      .then(setMeeting)
      .catch((err) => setErrorMessage("Failed to load meeting: " + err.message));

    return () => {
      cleanupAudio();
    };
  }, [meetingId]);

  // Elapsed timer
  useEffect(() => {
    if (recordingState === "recording") {
      timerRef.current = setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [recordingState]);

  // Visualizer loop
  function drawVisualizer(analyser) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function render() {
      animFrameRef.current = requestAnimationFrame(render);
      analyser.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = (canvas.width / bufferLength) * 2.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * canvas.height * 0.9;

        // Gradient
        const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
        gradient.addColorStop(0, "#3b82f6");
        gradient.addColorStop(1, "#8b5cf6");

        ctx.fillStyle = gradient;
        ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
        x += barWidth + 2;
      }
    }
    render();
  }

  async function startRecording() {
    try {
      setErrorMessage(null);
      // Capture the meeting tab/system audio separately from the microphone.
      // The browser asks the user to select the meeting tab and enable Share tab audio.
      const displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true
      });
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });
      streamRef.current = stream;
      displayStreamRef.current = displayStream;

      if (!displayStream.getAudioTracks().length) {
        displayStream.getTracks().forEach((track) => track.stop());
        stream.getTracks().forEach((track) => track.stop());
        throw new Error("Please enable Share tab audio when selecting the meeting tab.");
      }

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;

      const microphoneSource = audioCtx.createMediaStreamSource(stream);
      const meetingAudioSource = audioCtx.createMediaStreamSource(
        new MediaStream(displayStream.getAudioTracks())
      );
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      microphoneSource.connect(analyser);
      meetingAudioSource.connect(analyser);

      drawVisualizer(analyser);

      // WebSocket Connection
      const wsUrl = `${process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000"}/api/v1/meetings/${meetingId}/recording/stream`;
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected for live meeting");
        updateRecordingState("recording");
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "chunk_saved") {
            setSavedChunksCount(msg.chunk_index + 1);
          } else if (msg.type === "transcript") {
            const text = String(msg.text || "").trim();
            if (text && text !== lastTranscriptRef.current) {
              lastTranscriptRef.current = text;
              setInterimTranscripts((prev) => [...prev.slice(-49), text]);
            }
          }
        } catch (e) {
          // non-json
        }
      };

      ws.onerror = (e) => {
        console.error("WebSocket error:", e);
      };

      // ScriptProcessor for PCM16 audio capture
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (recordingStateRef.current !== "recording") return;
        const inputData = e.inputBuffer.getChannelData(0);
        // Convert Float32 to Int16 PCM
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        if (ws.readyState === WebSocket.OPEN) {
          ws.send(pcm16.buffer);
        }
      };

      // Multiple sources connected to one ScriptProcessor are mixed by the
      // Web Audio graph, while preserving both microphone and tab audio.
      microphoneSource.connect(processor);
      meetingAudioSource.connect(processor);
      processor.connect(audioCtx.destination);

      displayStream.getVideoTracks().forEach((track) => {
        track.onended = () => {
          if (recordingStateRef.current === "recording") stopAndProcess();
        };
      });
    } catch (err) {
      setErrorMessage("Microphone access failed: " + err.message);
    }
  }

  function pauseRecording() {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ command: "pause" }));
    }
    updateRecordingState("paused");
  }

  function resumeRecording() {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ command: "resume" }));
    }
    updateRecordingState("recording");
  }

  async function stopAndProcess() {
    updateRecordingState("stopping");

    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ command: "stop" }));
      socketRef.current.close();
    }
    cleanupAudio();

    try {
      await stopMeetingRecording(meetingId);
      router.push(`/meetings/${meetingId}`);
    } catch (err) {
      setErrorMessage("Error finalizing meeting: " + err.message);
      updateRecordingState("idle");
    }
  }

  function cleanupAudio() {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (processorRef.current) processorRef.current.disconnect();
    if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
    if (displayStreamRef.current) displayStreamRef.current.getTracks().forEach((t) => t.stop());
    if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
    if (socketRef.current) socketRef.current.close();
  }

  function formatTime(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    return `${hours.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  return (
    <div className="actionmic-page live-room-page">
      <Navbar />

      <main className="actionmic-container live-room-container">
        {/* Top Navigation */}
        <div className="live-room-header">
          <Link href={`/meetings/${meetingId}`} className="back-link">
            <ArrowLeft size={16} /> Exit to Workspace
          </Link>
          <div className="live-meeting-meta">
            <h1 className="live-meeting-title">{meeting?.title || "Live Meeting"}</h1>
            <span className="live-room-pill">
              <Radio size={14} className={recordingState === "recording" ? "pulse-icon" : ""} />
              {recordingState === "recording" ? "Live Stream Active" : recordingState === "paused" ? "Recording Paused" : "Ready"}
            </span>
          </div>
        </div>

        {errorMessage && <div className="modal-error mb-4">{errorMessage}</div>}

        {/* Central Recording Console */}
        <div className="live-console-card">
          {recordingState === "idle" && (
            <div className="capture-help">
              <strong>Two-way audio capture</strong>
              <span>When prompted, select the meeting tab and enable <b>Share tab audio</b>. This captures remote voices through headphones as well as your microphone.</span>
            </div>
          )}
          {/* Waveform Visualizer */}
          <div className="visualizer-wrapper">
            <canvas ref={canvasRef} width="600" height="120" className="waveform-canvas" />
          </div>

          {/* Big Timer */}
          <div className="live-timer-display">
            <span className="timer-digits">{formatTime(elapsedSeconds)}</span>
          </div>

          {/* Safety Persistence Tag */}
          <div className="persistence-indicator">
            <ShieldCheck size={16} className="shield-icon" />
            <span>
              Crash-Resilient Audio Engine: <strong>{savedChunksCount} chunks</strong> persisted directly to disk
            </span>
          </div>

          {/* Control Buttons */}
          <div className="live-control-buttons">
            {recordingState === "idle" && (
              <button onClick={startRecording} className="btn-big-record">
                <Mic size={24} />
                <span>Start Recording</span>
              </button>
            )}

            {recordingState === "recording" && (
              <>
                <button onClick={pauseRecording} className="btn-console-pause">
                  <Pause size={20} />
                  <span>Pause</span>
                </button>

                <button onClick={stopAndProcess} className="btn-console-stop">
                  <Square size={20} />
                  <span>Stop & Extract Intelligence</span>
                </button>
              </>
            )}

            {recordingState === "paused" && (
              <>
                <button onClick={resumeRecording} className="btn-console-resume">
                  <Play size={20} />
                  <span>Resume</span>
                </button>

                <button onClick={stopAndProcess} className="btn-console-stop">
                  <Square size={20} />
                  <span>Stop & Extract Intelligence</span>
                </button>
              </>
            )}

            {recordingState === "stopping" && (
              <div className="stopping-indicator">
                <div className="spinner"></div>
                <span>Assembling master recording and kicking off AI intelligence pipeline...</span>
              </div>
            )}
          </div>
        </div>

        {/* Live Speech Stream Box */}
        <div className="live-transcript-box">
          <div className="box-header">
            <FileText size={16} />
            <h3>Live Speech Recognition Stream</h3>
          </div>
          <div className="box-content">
            {interimTranscripts.length === 0 ? (
              <p className="placeholder-text">
                Speech recognition will display here in real time as attendees speak...
              </p>
            ) : (
              <div className="live-transcript-feed">
                {interimTranscripts.map((t, i) => (
                  <p key={i} className="live-token">{t}</p>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
