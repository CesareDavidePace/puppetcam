"""Put the face model inside the package, so the installed app never downloads it."""

from puppetcam.tracker import BUNDLED_MODEL, ensure_model

print(ensure_model(BUNDLED_MODEL))
