from enum import Enum


class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    SMUG = "smug"
    TEASING = "teasing"
    ANNOYED = "annoyed"
    ANGRY = "angry"
    SAD = "sad"
    CONCERNED = "concerned"
    AFFECTIONATE = "affectionate"
    PROUD = "proud"
    CONFUSED = "confused"
    SURPRISED = "surprised"
    EMBARRASSED = "embarrassed"
    TIRED = "tired"
    LAUGHING = "laughing"
    RELIEVED = "relieved"
    DISAPPOINTED = "disappointed"
    CURIOUS = "curious"
    SUSPICIOUS = "suspicious"
    BORED = "bored"
    PLAYFUL = "playful"
    SUPPORTIVE = "supportive"


class ExpressionIntent(Enum):
    NEUTRAL = "neutral"
    GREETING = "greeting"
    FAREWELL = "farewell"
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    CELEBRATION = "celebration"
    COMFORT = "comfort"
    ENCOURAGEMENT = "encouragement"
    PLAYFUL_TEASING = "playful_teasing"
    LIGHT_SCOLDING = "light_scolding"
    MOCKING = "mocking"
    CONFUSION = "confusion"
    SHOCK = "shock"
    AFFECTION = "affection"
    PRAISE = "praise"
    APOLOGY = "apology"
    THANKS = "thanks"
    WARNING = "warning"
    QUESTIONING = "questioning"
    REASSURANCE = "reassurance"
    REACTION = "reaction"


class BonusMedia(Enum):
    NONE = "none"
    AUTO = "auto"
    STICKER = "sticker"
    GIF = "gif"


class AssetType(Enum):
    EMOJI = "emoji"
    STICKER = "sticker"
    GIF = "gif"
