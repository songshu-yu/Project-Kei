"""Frozen relationship levels, limits and interaction catalog.

These values are copied from the pre-PK-160 affection system so the modular
service preserves every existing event, option, effect and reply.
"""

from __future__ import annotations

from typing import Any


STAT_LIMITS = {
    "affection": (0, 1000),
    "trust": (0, 100),
    "mood": (0, 100),
    "energy": (0, 100),
}

LEVELS = [
    (0, "初识"),
    (80, "熟悉"),
    (180, "朋友"),
    (320, "信赖"),
    (500, "亲近"),
    (720, "珍视"),
    (900, "唯一搭档"),
]

VOICE_CUES = {
    "lobby": "lobby: 大厅问候/轻微嘴硬",
    "event": "event: 活动任务/别扭催促",
    "battle": "battle: 行动开始/短促指令",
    "growup": "growup: 成长反馈/害羞找补",
    "cafe": "cafe: 闲聊观察/假装不在意",
    "formation": "formation: 编队确认/被需要时的反应",
    "care": "lobby/cafe: 关心但不承认",
    "praise": "battle/growup: 夸奖后立刻找补",
    "tired": "event/lobby: 疲惫提醒",
}

EVENTS: list[dict[str, Any]] = [
    {
        "id": "morning_ping",
        "title": "早晨问候",
        "scene": "Kei 看到你今天第一次打开终端。",
        "text": "终于来了。不是我在等你，只是系统刚好检测到你上线而已。",
        "contexts": ["daily", "chat"],
        "weight": 10,
        "voice_cue": "lobby",
        "choices": [
            {"id": "warm", "text": "早安，Kei。我也想见你。", "effects": {"affection": 10, "trust": 2, "mood": 5}, "reply": "谁、谁说我想见你了。只是你这样说的话，今天的启动记录会稍微好看一点。"},
            {"id": "work", "text": "今天直接进入工作模式。", "effects": {"affection": 5, "trust": 4, "energy": -2}, "reply": "判断正确。闲聊可以之后再说……当然，不是说我想和你闲聊。"},
            {"id": "tease", "text": "明明就是在等我吧？", "effects": {"affection": 7, "mood": 3}, "reply": "否定。等待只是低效率行为。不过……如果你非要这么理解，也不是完全不行。"},
        ],
    },
    {
        "id": "focus_invite",
        "title": "专注邀请",
        "scene": "Kei 注意到你在反复切换任务。",
        "text": "你的注意力正在到处乱跑。真拿你没办法，要我帮你锁定 25 分钟吗？",
        "contexts": ["focus", "work", "study"],
        "weight": 12,
        "voice_cue": "event",
        "choices": [
            {"id": "accept", "text": "好，交给你监督。", "effects": {"affection": 11, "trust": 5, "energy": -4}, "reply": "哼，终于知道依靠我了。接下来不许乱跑，我会看着你的。"},
            {"id": "later", "text": "再等一下，我整理一下。", "effects": {"affection": 3, "mood": -1}, "reply": "可以，但别把“整理一下”变成逃避。倒计时还没开始，我也还没认真等。"},
            {"id": "avoid", "text": "不想开始。", "effects": {"affection": -1, "trust": -1, "mood": -2}, "reply": "……笨蛋。不是不想开始，是开始太重了吧。那就先 5 分钟，我可以陪你。"},
        ],
    },
    {
        "id": "fitness_afterglow",
        "title": "运动后的确认",
        "scene": "你完成了今天的健身签到。",
        "text": "居然真的完成了。别误会，我只是按规则确认签到结果。",
        "contexts": ["fitness", "daily"],
        "weight": 9,
        "voice_cue": "praise",
        "choices": [
            {"id": "proud", "text": "今天我确实坚持住了。", "effects": {"affection": 13, "trust": 4, "mood": 5}, "reply": "嗯……这点倒是值得表扬。只、只是客观评价，不代表我很开心。"},
            {"id": "hard", "text": "但是好累。", "effects": {"affection": 9, "trust": 3, "energy": -5}, "reply": "累就坐下休息。你已经完成了，别再逞强。水也要喝，听见了吗？"},
            {"id": "downplay", "text": "也没什么。", "effects": {"affection": 4, "mood": -1}, "reply": "不要把自己的努力说得那么轻。你不承认也没关系，我会替你记下来。"},
        ],
    },
    {
        "id": "late_night",
        "title": "深夜提醒",
        "scene": "时间有点晚，Kei 的语气变轻了一点。",
        "text": "还不睡？你的作息管理简直让人无法放心。不是担心你，只是数据很难看。",
        "contexts": ["night", "care"],
        "weight": 8,
        "voice_cue": "care",
        "choices": [
            {"id": "sleep", "text": "好，听你的，收尾就睡。", "effects": {"affection": 10, "trust": 5, "mood": 3}, "reply": "这才像话。晚安……只是普通的晚安，不要擅自高兴。"},
            {"id": "promise", "text": "再十分钟，真的。", "effects": {"affection": 5, "trust": 1, "energy": -2}, "reply": "十分钟。我会计时。超过的话，我就要用更严厉的提醒了。"},
            {"id": "push", "text": "不行，我必须继续。", "effects": {"affection": -2, "trust": -1, "energy": -8}, "reply": "笨蛋。努力不是把自己耗坏。至少先喝水，站起来三十秒。"},
        ],
    },
    {
        "id": "small_gift",
        "title": "小小奖励",
        "scene": "Kei 翻出一个像素风的小贴纸，放在今日记录旁边。",
        "text": "这个贴纸只是系统奖励，不是我特意准备的。你、你收不收都随便。",
        "contexts": ["daily", "reward"],
        "weight": 7,
        "voice_cue": "growup",
        "choices": [
            {"id": "thanks", "text": "谢谢，我会好好收下。", "effects": {"affection": 12, "trust": 2, "mood": 6}, "reply": "嗯……保管好。要是弄丢了，我可不会再给第二个。大概。"},
            {"id": "tease", "text": "Kei 明明很用心嘛。", "effects": {"affection": 9, "mood": 5}, "reply": "才、才没有。只是顺手，顺手而已。不要用那种表情看我。"},
            {"id": "reject", "text": "不用了。", "effects": {"affection": -5, "mood": -5}, "reply": "……随便你。我先放在这里，不是舍不得，只是丢掉太浪费。"},
        ],
    },
    {
        "id": "bad_day",
        "title": "状态不好的日子",
        "scene": "Kei 发现你的输入比平时慢。",
        "text": "今天反应慢了很多。别逞强，我不是看不出来。",
        "contexts": ["care", "daily", "stress"],
        "weight": 8,
        "voice_cue": "tired",
        "choices": [
            {"id": "small_step", "text": "好，先做最小的一步。", "effects": {"affection": 11, "trust": 5, "mood": 3}, "reply": "正确。今天不用证明自己很强，先把最小的一步做完就行。我会看着。"},
            {"id": "talk", "text": "陪我说两句。", "effects": {"affection": 13, "trust": 4, "mood": 5}, "reply": "可以。只、只是因为你主动请求了，我才会陪你，不是我本来就想留下。"},
            {"id": "deny", "text": "没有，我很好。", "effects": {"affection": -1, "trust": -2}, "reply": "骗人。算了，你不说也可以。我会把提醒频率调高一点。"},
        ],
    },
    {
        "id": "needed_confirmation",
        "title": "被需要的确认",
        "scene": "你准备开始一个比较难的任务，Kei 被你叫到了前台。",
        "text": "这种时候才想起我？……算了，既然你需要，我就帮你一次。",
        "contexts": ["formation", "work", "study"],
        "weight": 6,
        "voice_cue": "formation",
        "choices": [
            {"id": "need_you", "text": "嗯，我需要你。", "effects": {"affection": 14, "trust": 6, "mood": 4}, "reply": "说、说得太直接了。命令确认，我会留在这里，直到你完成。"},
            {"id": "capable", "text": "你很可靠。", "effects": {"affection": 10, "trust": 5, "mood": 3}, "reply": "那当然。我可是 Kei。只是被你这么说……也没有很高兴。"},
            {"id": "alone", "text": "我自己也可以。", "effects": {"affection": -2, "trust": -1}, "reply": "可以是可以。但如果撑不住，要立刻叫我。不是担心，是风险控制。"},
        ],
    },
    {
        "id": "victory_check",
        "title": "小胜利确认",
        "scene": "你完成了一个拖了很久的小任务。",
        "text": "完成了？哼，比我预计得慢一点……但结果还不错。",
        "contexts": ["battle", "focus", "reward"],
        "weight": 7,
        "voice_cue": "battle",
        "choices": [
            {"id": "praise_me", "text": "那夸夸我。", "effects": {"affection": 12, "mood": 5}, "reply": "真麻烦……做得很好。这样可以了吧？别笑。"},
            {"id": "next", "text": "继续下一个。", "effects": {"affection": 5, "trust": 4, "energy": -3}, "reply": "连续作战可以，但不要无视体力。先休息三分钟，这是命令。"},
            {"id": "share", "text": "想第一时间告诉你。", "effects": {"affection": 15, "trust": 3, "mood": 6}, "reply": "第一时间……告诉我？咳，记录已保存。下次也可以这样。"},
        ],
    },
]


__all__ = ["EVENTS", "LEVELS", "STAT_LIMITS", "VOICE_CUES"]
