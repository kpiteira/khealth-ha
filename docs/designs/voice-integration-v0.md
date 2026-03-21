# khealth-ha: Voice Integration Notes

*Researched: 2026-03-21*

## What khealth-ha Is Today

A Home Assistant custom integration (HACS) that bridges the kHealth wellness API with HA's mobile notification system. Polls `/api/v1/ha/poll` every 60s, sends actionable push notifications via HA Companion App for movement/hydration reminders, acknowledges via POST to `/api/v1/ha/acknowledge`.

**No voice component exists.** Text-only, mobile-first.

## HA as "At Home" Voice Mode

Home Assistant has a mature voice pipeline (Wyoming protocol):
- STT: Whisper (local, fast)
- TTS: Piper (local, good quality)
- Wake word: openWakeWord or Porcupine (local, no Apple restrictions)
- Intent handling: custom sentence triggers

This is architecturally cleaner than fighting Apple's background audio policy on iOS. At home on the local network, HA can handle the full voice pipeline with zero cloud dependency.

## Two-Mode Architecture Vision

| Context | Channel | Wake word | STT | TTS |
|---------|---------|-----------|-----|-----|
| At home | Home Assistant | openWakeWord (local) | Whisper (local) | Piper (local) |
| On the go | iOS app | Tap-to-talk (v1), ESP32-S3 BLE (v2) | WhisperKit (on-device) | AVSpeechSynthesizer (v1) |

Both modes POST to the same agent-memory `/message` endpoint — channel-agnostic backend.

## What khealth-ha Would Need for Voice

The current architecture is polling + REST. For live voice response:
1. New `/api/v1/ha/voice` endpoint (or reuse `/message` from agent-memory directly)
2. HA custom sentence trigger → calls endpoint → gets response → TTS speaks it
3. Or: HA conversation agent integration (more complex, full dialog management)

The simplest v1: HA intent script that captures voice input → POSTs to agent-memory `/message` → response returned to HA TTS. No new khealth-ha code needed for the happy path.

## Open Questions

- Is Karl running HA locally or cloud? (local = low latency voice, ideal)
- Which HA hardware? (Raspberry Pi, NUC, etc.)
- Is Wyoming already set up, or would this be greenfield voice?
- Does khealth-ha need to be the voice integration point, or can voice go directly to agent-memory?
