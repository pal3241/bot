# SENA Vision / Expression Engine

This module adds the backend-independent foundation for camera-driven SENA
reactions.

## Pipeline

`camera/CV backend -> VisionObservation -> ExpressionEventEngine -> semantic intent -> existing expression resolver -> emoji/sticker/GIF`

The important boundary is **semantic intent**. Vision never chooses a Discord
emoji/sticker ID or a GIF URL. The existing expression subsystem remains the
single place that resolves and sends media.

## Calibration

A backend should collect neutral face blendshape samples for several seconds,
call `add_neutral_sample()` for each frame, then `finish_calibration()`. Runtime
blendshapes are converted to z-scores relative to that user's neutral face.
This avoids assuming that every person's neutral MediaPipe values are equal.

## Optional backend

No OpenCV/MediaPipe dependency is added to the core requirements yet. SENA is
currently designed to run on desktop and Android/Termux; computer-vision wheels
are platform-sensitive and must not make the Discord bot fail to install. A
future desktop backend can depend on MediaPipe/OpenCV as an optional extra and
feed this stable API.

## Example

```python
from vision import ExpressionEventEngine, VisionObservation

engine = ExpressionEventEngine()
# During calibration:
engine.add_neutral_sample({"jawOpen": 0.04, "mouthSmileLeft": 0.1})
# ...collect >= 15 frames...
engine.finish_calibration()

# During runtime:
event = engine.process(VisionObservation(
    blendshapes={"jawOpen": 0.8, "eyeWideLeft": 0.7, "eyeWideRight": 0.7},
))
if event:
    # Feed event.intent to SENA's expression resolver/service.
    print(event.intent)
```

The engine also accepts backend gesture labels such as `heart`, `hand_up`,
`side_eye`, `tongue_out`, and `facepalm` and maps them to SENA semantic intents.
