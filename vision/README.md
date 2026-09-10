# SENA Vision / Expression Engine

SENA Vision turns local webcam expressions and hand gestures into the same
semantic expression requests already used by SENA's Discord expression system.
It does **not** hard-code Discord emoji IDs or GIF URLs.

## Pipeline

`webcam -> MediaPipe -> VisionObservation -> calibrated event engine -> semantic intent -> ExpressionRequest -> existing resolver/sender -> emoji/sticker/GIF`

The semantic boundary is deliberate: the CV layer only says things such as
`shocked`, `love`, `suspicious`, or `playful`; the existing expression catalog
still decides the concrete Discord media.

## Desktop setup

Install the normal bot dependencies first, then the optional CV set:

```bash
pip install -r requirements.txt
pip install -r requirements-vision.txt
```

Vision currently uses MediaPipe 1.0.1 so Python 3.13 desktop environments can
install a compatible wheel. The optional requirements remain separate because
MediaPipe/OpenCV must not break Android/Termux installation.

Optional `.env` tuning:

```env
SENA_VISION_CAMERA_INDEX=0
SENA_VISION_CALIBRATION_SECONDS=5
SENA_VISION_COOLDOWN_SECONDS=6
```

There is no Vision Discord channel ID setting. Start SENA normally and open
**Vision / Webcam**. Use `channel` to choose the server/text channel from a
menu, then use `start`. If no text channel has been selected yet, `start`
automatically opens the same channel picker.

Changing the Vision output channel while detection is active safely stops the
old worker, switches the destination, and starts the worker again.

The **Voice** tab remains separate: its Discord Voice Transport panel already
lets you choose a guild and voice channel and provides **Join** / **Leave**
controls. Voice channel selection does not require typing a Discord channel ID.

## First-run calibration

If `data/vision_calibration.json` does not exist, Vision asks you to look at the
camera with a neutral face for a few seconds. It records the mean and standard
deviation for each face blendshape. Runtime values are then converted to
z-scores relative to *your* neutral face rather than compared only to universal
raw thresholds.

Calibration is persisted locally and ignored by git. Use `recalibrate` in the
Vision menu whenever lighting/camera/user changes significantly.

## Current reactions

Facial events:

- smile -> `happy`
- wide eyes + open jaw -> `shocked`
- nose sneer -> `disgusted`

Gesture events:

- two-hand heart -> `love`
- raised open palm -> `greeting`
- side-eye -> `suspicious`
- tongue out -> `playful`
- open palm over face -> `facepalm`

The event engine requires the same candidate for multiple frames and applies a
per-intent cooldown, reducing one-frame detector noise and Discord spam.

## Failure isolation

`cv2` and `mediapipe` are imported lazily only when the webcam backend starts.
If the optional dependencies, models, or camera are unavailable, Vision fails
in isolation; the main Discord bot and Termux-compatible features remain
usable.

MediaPipe face/hand task models are downloaded into `models/vision/` on first
use. That directory is ignored by git.

## Files

- `engine.py` — calibration, z-scores, event arming/cooldown
- `mediapipe_backend.py` — webcam + MediaPipe face/hand inference
- `expression_bridge.py` — semantic event -> SENA `ExpressionRequest`
- `service.py` — background worker + proactive Discord dispatch
- `features/vision.py` — terminal feature controller + channel picker
