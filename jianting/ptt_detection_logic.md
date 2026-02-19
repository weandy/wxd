
# PTT Detection Logic

## Overview
To detect real-time PTT (Push-to-Talk) status without explicit signaling packets, we utilize the RTSP/RTP protocol features and heuristics.

## PTT Press (Start)
- **Mechanism**: RTP Marker Bit (M)
- **Logic**: The first packet of a talkspurt often has the Marker bit set to 1.
- **Implementation**: `bsht_client.py` propagates the marker bit from `RTPPacket` to `AudioFrame`. `BotServer` checks `frame.end_marker`. If True, it logs "🟢 PTT Press".

## PTT Release (End)
- **Mechanism**: Timeout / Silence Detection
- **Logic**: Since UDP is connectionless and there's no explicit "Stop" packet (or at least we rely on RTP), we assume PTT is released if no audio packets are received from the current speaker for a short duration (e.g., 500ms).
- **Implementation**: `BotServer` main loop checks `time.time() - self.last_audio_time`. If > 0.5s, logs "🔴 PTT Release".

## Simultaneous Speakers
- The RTP SSRC allows distinguishing streams.
- Current `BotServer` implementation tracks a single `current_speaker` for logging purposes to avoid console spam, but `AudioStreamListener` processes all incoming packets.
