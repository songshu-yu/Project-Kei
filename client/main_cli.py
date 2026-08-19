"""main_cli.py — 命令行聊天客户端。cd server && python ../client/main_cli.py"""
import os, sys, asyncio, subprocess, platform, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from llm_engine import LLMEngine
from tts_client import TTSClient, TTSConfig
from fitness_checkin import check_in as fitness_check_in, get_status as fitness_status
from focus_timer import get_status as focus_timer_status, start_timer, stop_timer
from affection_system import choose_response as affection_choose, get_status as affection_status, trigger_event as affection_trigger

EMOJIS = {"happy":"😊","shy":"😳","calm":"😌","angry":"😤","sad":"😢","surprised":"😲"}

def play_audio(data):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(data); tmp.close()
    s = platform.system()
    try:
        if s=="Darwin": subprocess.run(["afplay",tmp.name])
        elif s=="Linux": subprocess.run(["aplay",tmp.name])
        elif s=="Windows": os.startfile(tmp.name)
    except: print("  (⚠️ 无播放器)")
    finally: os.unlink(tmp.name)

async def main():
    print("\n╔══════════════════════════════════════════╗")
    print("║      Project Kei — 命令行对话模式        ║")
    print("║ /quit 退出 | /clear 清空 | /history 记录 ║")
    print("║ /checkin 健身签到 | /fitness 查看连续天数 ║")
    print("║ /pomodoro 任务 | /focus 任务 | /timer 状态 ║")
    print("║ /event 场景 | /choose 选项 | /affection 好感 ║")
    print("╚══════════════════════════════════════════╝\n")
    api_key = os.getenv("LLM_API_KEY","")
    if not api_key or api_key == "sk-your-api-key-here":
        print("⚠️ 请设置 LLM_API_KEY 环境变量！")
        print("  export LLM_API_KEY=sk-xxx")
        print("  export LLM_BASE_URL=https://api.deepseek.com/v1  # 可选")
        print("  export LLM_MODEL=deepseek-chat                   # 可选")
        return
    llm = LLMEngine(api_key=api_key, base_url=os.getenv("LLM_BASE_URL","https://api.openai.com/v1"), model=os.getenv("LLM_MODEL","gpt-4o-mini"))
    tts = TTSClient(TTSConfig(
        host=os.getenv("TTS_HOST","localhost"),
        port=int(os.getenv("TTS_PORT","9880")),
        default_ref_audio=os.getenv("TTS_DEFAULT_REF_AUDIO","ref_audio/default.wav"),
        default_ref_text=os.getenv("TTS_DEFAULT_REF_TEXT",""),
        text_lang=os.getenv("TTS_TEXT_LANG","zh"),
        prompt_lang=os.getenv("TTS_PROMPT_LANG","zh"),
        api_style=os.getenv("TTS_API_STYLE","gptsovits"),
    ))
    tts_ok = await tts.check_available()
    print("—— kei 已上线，开始聊天吧！——\n")
    try:
        while True:
            try: ui = input("👤 你: ").strip()
            except EOFError: break
            if not ui: continue
            if ui=="/quit": print("\n💬 kei: 老师再见……下次再聊哦！"); break
            elif ui=="/clear": llm.clear_history(); continue
            elif ui=="/history": print(f"\n{llm.get_history_summary()}\n"); continue
            elif ui=="/affection":
                status = affection_status()
                level = status["level"]
                print(
                    f"\n😌 kei: 当前好感 {status['affection']}，阶段「{level['name']}」。"
                    f"信赖 {status['trust']}，心情 {status['mood']}，精力 {status['energy']}。\n"
                )
                continue
            elif ui.startswith("/event"):
                context = ui[len("/event"):].strip()
                result = affection_trigger(context=context)
                event = result.event
                print(f"\n😌 kei: {event['title']}")
                print(f"场景：{event['scene']}")
                print(f"Kei：{event['text']}")
                print(f"语音参考：{event.get('voice_cue_description','')}")
                for choice in event["choices"]:
                    print(f"  /choose {choice['id']}  {choice['text']}")
                print()
                continue
            elif ui.startswith("/choose"):
                choice_id = ui[len("/choose"):].strip()
                if not choice_id:
                    print("\n😌 kei: 要告诉我选择哪个选项，比如 /choose warm\n")
                    continue
                result = affection_choose(choice_id)
                print(f"\n😊 kei: {result.reply or result.message}")
                print(f"变化：{result.effects}")
                print(f"当前好感：{result.stats['affection']}，阶段：{result.stats['level']['name']}\n")
                if result.reply and tts_ok:
                    audio = await tts.synthesize(result.reply, "happy")
                    if audio: play_audio(audio)
                continue
            elif ui=="/timer":
                result = focus_timer_status()
                print(f"\n😌 kei: {result.message}\n")
                continue
            elif ui=="/stopfocus":
                result = stop_timer()
                print(f"\n😌 kei: {result.message}\n")
                continue
            elif ui.startswith("/pomodoro"):
                task = ui[len("/pomodoro"):].strip()
                result = start_timer(mode="pomodoro", task=task)
                print(f"\n😌 kei: {result.message}\n")
                if result.started and tts_ok:
                    audio = await tts.synthesize(result.message, "calm")
                    if audio: play_audio(audio)
                continue
            elif ui.startswith("/focus"):
                task = ui[len("/focus"):].strip()
                result = start_timer(mode="focus", task=task)
                print(f"\n😌 kei: {result.message}\n")
                if result.started and tts_ok:
                    audio = await tts.synthesize(result.message, "calm")
                    if audio: play_audio(audio)
                continue
            elif ui=="/fitness":
                status = fitness_status()
                print(
                    f"\n💬 kei: 今天{'已经' if status['checked_today'] else '还没有'}健身签到。"
                    f"当前连续 {status['streak']} 天，距离下一次奖励还差 {status['next_reward_in']} 天。\n"
                )
                continue
            elif ui=="/checkin":
                result = fitness_check_in(note="checked in from main_cli")
                if result.reward_unlocked:
                    print(f"\n😊 kei: {result.reward_text}\n")
                    if tts_ok:
                        audio = await tts.synthesize(result.reward_text, "happy")
                        if audio: play_audio(audio)
                elif result.already_checked_in:
                    print(f"\n😌 kei: 今天已经签到过啦。当前连续 {result.streak} 天，奖励还差 {result.next_reward_in} 天。\n")
                else:
                    print(f"\n😌 kei: 健身签到完成。当前连续 {result.streak} 天，奖励还差 {result.next_reward_in} 天。\n")
                continue
            reply = await llm.chat(ui)
            print(f"{EMOJIS.get(reply.emotion,'💬')} kei: {reply.content}")
            if tts_ok:
                audio = await tts.synthesize(reply.content, reply.emotion)
                if audio: play_audio(audio)
            print()
    except KeyboardInterrupt: print("\n\n💬 kei: 老师突然走了……下次见哦……")
    finally: await llm.close(); await tts.close()

if __name__ == "__main__": asyncio.run(main())
