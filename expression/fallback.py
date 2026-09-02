from expression.enums import Emotion


UNICODE_BY_EMOTION: dict[Emotion, str] = {
    Emotion.NEUTRAL: "🙂",
    Emotion.HAPPY: "😊",
    Emotion.EXCITED: "✨",
    Emotion.SMUG: "😏",
    Emotion.TEASING: "😼",
    Emotion.ANNOYED: "🙄",
    Emotion.ANGRY: "😠",
    Emotion.SAD: "😔",
    Emotion.CONCERNED: "😟",
    Emotion.AFFECTIONATE: "💜",
    Emotion.PROUD: "😌",
    Emotion.CONFUSED: "🤨",
    Emotion.SURPRISED: "😳",
    Emotion.EMBARRASSED: "😳",
    Emotion.TIRED: "😴",
    Emotion.LAUGHING: "😂",
    Emotion.RELIEVED: "😮‍💨",
    Emotion.DISAPPOINTED: "😕",
    Emotion.CURIOUS: "🤔",
    Emotion.SUSPICIOUS: "🧐",
    Emotion.BORED: "😑",
    Emotion.PLAYFUL: "😼",
    Emotion.SUPPORTIVE: "💪",
}


def unicode_fallback(emotion: Emotion) -> str:
    return UNICODE_BY_EMOTION.get(emotion, "🙂")
