"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_BASE || "ws://127.0.0.1:8000";

export default function LiveRecorder({
  patientId,
  clinician,
  role,
  onComplete,
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [statusMsg, setStatusMsg] = useState("Ready to record");
  const [transcript, setTranscript] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const [finishing, setFinishing] = useState(false);
  const [audioId, setAudioId] = useState(null);
  const [volumeLevel, setVolumeLevel] = useState(0);

  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const processorNodeRef = useRef(null);
  const silentGainRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const isRecordingRef = useRef(false);  // ref to avoid stale closure in ws.onclose
  const isPausedRef = useRef(false);
  const sampleRateRef = useRef(16000);

  // Map speaker IDs from backend (SPEAKER_00, SPEAKER_01) to human-readable labels
  function getSpeakerDisplay(speakerId) {
    if (!speakerId) return { label: "Speaker", icon: "👤", cssClass: "speaker-other" };
    // Already human-readable
    if (speakerId === "Doctor") return { label: "Doctor", icon: "🩺", cssClass: "speaker-doctor" };
    if (speakerId === "Patient") return { label: "Patient", icon: "🧑", cssClass: "speaker-patient" };
    // SPEAKER_XX format from backend
    if (speakerId.startsWith("SPEAKER_")) {
      const num = parseInt(speakerId.replace("SPEAKER_", ""), 10);
      if (num === 0) return { label: "Speaker 1", icon: "🩺", cssClass: "speaker-doctor" };
      if (num === 1) return { label: "Speaker 2", icon: "🧑", cssClass: "speaker-patient" };
      return { label: `Speaker ${num + 1}`, icon: "👤", cssClass: "speaker-other" };
    }
    return { label: speakerId, icon: "👤", cssClass: "speaker-other" };
  }

  // ----------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------

  const cleanup = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);

    if (processorNodeRef.current) {
      processorNodeRef.current.onaudioprocess = null;
      try {
        processorNodeRef.current.disconnect();
      } catch {
        // ignore disconnect errors during cleanup
      }
      processorNodeRef.current = null;
    }

    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {
        // ignore disconnect errors during cleanup
      }
      sourceNodeRef.current = null;
    }

    if (silentGainRef.current) {
      try {
        silentGainRef.current.disconnect();
      } catch {
        // ignore disconnect errors during cleanup
      }
      silentGainRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close();
    }
  }, []);

  useEffect(() => {
    return cleanup; // cleanup on unmount
  }, [cleanup]);

  // ----------------------------------------------------------
  // Volume meter
  // ----------------------------------------------------------
  function startVolumeMeter(stream) {
    try {
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const data = new Uint8Array(analyser.frequencyBinCount);

      function tick() {
        analyser.getByteFrequencyData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i];
        setVolumeLevel(Math.min(100, Math.round((sum / data.length / 255) * 100 * 3)));
        animFrameRef.current = requestAnimationFrame(tick);
      }
      tick();
    } catch {
      // AudioContext may not be available
    }
  }

  // ----------------------------------------------------------
  // Start recording
  // ----------------------------------------------------------
  async function handleStart() {
    setError(null);
    setTranscript([]);
    setElapsed(0);
    setStatusMsg("Connecting…");
    setAudioId(null);
    setFinishing(false);

    // 1. Get mic access before opening the WebSocket so we only create a
    // live session when recording is actually possible.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });
      streamRef.current = stream;
      startVolumeMeter(stream);

      // 3. Open WebSocket only after the mic is confirmed.
      const wsUrl = `${WS_URL}/ws/live-record`;
      console.log("🔌 Connecting to WebSocket:", wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("✅ WebSocket opened, sending start message...");

        const audioContext = new AudioContext();
        audioContextRef.current = audioContext;
        sampleRateRef.current = audioContext.sampleRate;

        const sourceNode = audioContext.createMediaStreamSource(stream);
        const processorNode = audioContext.createScriptProcessor(4096, 1, 1);
        const silentGain = audioContext.createGain();
        silentGain.gain.value = 0;

        sourceNode.connect(processorNode);
        processorNode.connect(silentGain);
        silentGain.connect(audioContext.destination);

        sourceNodeRef.current = sourceNode;
        processorNodeRef.current = processorNode;
        silentGainRef.current = silentGain;

        processorNode.onaudioprocess = (event) => {
          if (!isRecordingRef.current || isPausedRef.current) return;
          if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

          const input = event.inputBuffer.getChannelData(0);
          const pcm16 = new Int16Array(input.length);

          for (let i = 0; i < input.length; i++) {
            const sample = Math.max(-1, Math.min(1, input[i]));
            pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
          }

          wsRef.current.send(pcm16.buffer);
        };

        ws.send(
          JSON.stringify({
            type: "start",
            patient_id: patientId,
            clinician: clinician,
            sample_rate: audioContext.sampleRate,
          })
        );
        console.log("📤 Sent start message:", { patient_id: patientId, clinician: clinician });

        setIsRecording(true);
        isRecordingRef.current = true;
        isPausedRef.current = false;
        setStatusMsg("🔴 Recording…");

        // Start elapsed timer
        const start = Date.now();
        timerRef.current = setInterval(() => {
          setElapsed(Math.floor((Date.now() - start) / 1000));
        }, 500);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === "connected") {
            // WebSocket connection confirmed
            console.log("✅ WebSocket connected:", msg.message);
          } else if (msg.type === "transcript") {
            setTranscript(msg.data);
            console.log("📝 Received transcript update:", msg.data.length, "segments");
          } else if (msg.type === "status") {
            setStatusMsg(msg.message);
            console.log("📊 Status:", msg.message);
          } else if (msg.type === "done") {
            setAudioId(msg.audio_id);
            setStatusMsg("✅ Processing complete!");
            setFinishing(false);
            console.log("✅ Processing complete! Audio ID:", msg.audio_id);
          } else if (msg.type === "error") {
            setError(msg.message);
            setFinishing(false);
            console.error("❌ Error:", msg.message);
          } else if (msg.type === "ping") {
            // Respond to server ping to keep connection alive
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "pong" }));
            }
          }
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onerror = (err) => {
        console.error("❌ WebSocket error:", err);
        setError("WebSocket connection failed. Is the backend running?");
      };

      ws.onclose = (event) => {
        console.log("🔌 WebSocket closed:", event.code, event.reason);
        if (isRecordingRef.current) {
          setIsRecording(false);
          isRecordingRef.current = false;
          setStatusMsg("Connection closed");
        }
      };
    } catch (micErr) {
      setError("Microphone access denied: " + micErr.message);
    }
  }

  // ----------------------------------------------------------
  // Pause / Resume
  // ----------------------------------------------------------
  function handlePause() {
    if (!audioContextRef.current) return;
    if (!isPausedRef.current) {
      isPausedRef.current = true;
      audioContextRef.current.suspend().catch(() => {});
      setIsPaused(true);
      setStatusMsg("⏸️ Paused");
    }
  }

  function handleResume() {
    if (!audioContextRef.current) return;
    if (isPausedRef.current) {
      isPausedRef.current = false;
      audioContextRef.current.resume().catch(() => {});
      setIsPaused(false);
      setStatusMsg("🔴 Recording…");
    }
  }

  // ----------------------------------------------------------
  // Stop recording
  // ----------------------------------------------------------
  function handleStop() {
    setIsRecording(false);
    setIsPaused(false);
    setFinishing(true);
    isRecordingRef.current = false;
    isPausedRef.current = false;
    setStatusMsg("Stopping recording & processing…");

    if (timerRef.current) clearInterval(timerRef.current);
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);

    const ws = wsRef.current;

    if (processorNodeRef.current) {
      processorNodeRef.current.onaudioprocess = null;
      try {
        processorNodeRef.current.disconnect();
      } catch {
        // ignore disconnect errors during shutdown
      }
      processorNodeRef.current = null;
    }

    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {
        // ignore disconnect errors during shutdown
      }
      sourceNodeRef.current = null;
    }

    if (silentGainRef.current) {
      try {
        silentGainRef.current.disconnect();
      } catch {
        // ignore disconnect errors during shutdown
      }
      silentGainRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
  }

  // ----------------------------------------------------------
  // Format mm:ss
  // ----------------------------------------------------------
  function fmtTime(sec) {
    const m = Math.floor(sec / 60)
      .toString()
      .padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------
  return (
    <div className="live-recorder">
      {/* Header card */}
      <div className="live-header-card">
        <div className="live-meta">
          <span className="live-meta-item">
            <strong>Patient:</strong> {patientId}
          </span>
          <span className="live-meta-item">
            <strong>Clinician:</strong> {clinician}
          </span>
        </div>

        {/* Status & timer */}
        <div className="live-status-row">
          <span className={`live-status-badge ${isRecording ? "recording" : finishing ? "finishing" : audioId ? "done" : ""}`}>
            {statusMsg}
          </span>
          <span className="live-timer">{fmtTime(elapsed)}</span>
        </div>

        {/* Volume meter */}
        {isRecording && (
          <div className="live-volume-bar-wrapper">
            <div
              className="live-volume-bar"
              style={{ width: `${volumeLevel}%` }}
            />
          </div>
        )}

        {/* Controls */}
        <div className="live-controls">
          {!isRecording && !finishing && !audioId && (
            <button className="live-btn start" onClick={handleStart}>
              🎙️ Start Recording
            </button>
          )}

          {isRecording && !isPaused && (
            <>
              <button className="live-btn pause" onClick={handlePause}>
                ⏸️ Pause
              </button>
              <button className="live-btn stop" onClick={handleStop}>
                ⏹️ Stop & Process
              </button>
            </>
          )}

          {isRecording && isPaused && (
            <>
              <button className="live-btn resume" onClick={handleResume}>
                ▶️ Resume
              </button>
              <button className="live-btn stop" onClick={handleStop}>
                ⏹️ Stop & Process
              </button>
            </>
          )}

          {finishing && (
            <div className="live-finishing">
              <div className="processing-spinner" />
              <span>Running full ML pipeline…</span>
            </div>
          )}

          {audioId && (
            <button
              className="live-btn view-result"
              onClick={() => onComplete(audioId)}
            >
              📋 View Consultation Result
            </button>
          )}
        </div>

        {error && <p className="live-error">❌ {error}</p>}
      </div>

      {/* Live transcript panel */}
      <div className="live-transcript-panel">
        <h3 className="live-transcript-title">
          📝 Live Transcript
          {transcript.length > 0 && (
            <span className="live-segment-count">
              {transcript.length} segment{transcript.length !== 1 ? "s" : ""}
            </span>
          )}
        </h3>

        {transcript.length === 0 ? (
          <div className="live-transcript-empty">
            {isRecording
              ? "Listening… transcript will appear here as you speak."
              : "No transcript yet."}
          </div>
        ) : (
          <div className="live-transcript-list">
            {transcript.map((seg, idx) => {
              const speaker = getSpeakerDisplay(seg.speaker);
              return (
                <div
                  key={idx}
                  className={`transcript-line-enhanced ${speaker.cssClass}`}
                >
                  <div className="transcript-header-enhanced">
                    <div className="speaker-info">
                      <span className="speaker-badge">
                        {speaker.icon}
                      </span>
                      <span className="speaker-name">{speaker.label}</span>
                    </div>
                    {seg.start !== undefined && (
                      <span className="timestamp-badge">
                        {fmtTime(Math.round(seg.start))} –{" "}
                        {fmtTime(Math.round(seg.end))}
                      </span>
                    )}
                  </div>
                  <p className="transcript-text-enhanced">{seg.text}</p>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
