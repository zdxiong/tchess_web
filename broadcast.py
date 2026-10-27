# -*- coding: utf-8 -*-
"""
象棋直播口语播报：行棋前用豆包女声自动讲解当前这一手。

流程：轮询 http://127.0.0.1:8787/api/state
  -> 复用 tactic_commentator 拿到 口语走法 + 开局名 + 战术
  -> 火山方舟大模型(LLM) 生成连贯、带语气的主播台词
  -> 豆包语音(TTS) 合成语音 -> 本机播放

用法：
  1) 填好下方 key（或设环境变量）
  2) 启动应用 + 加载引擎 + 开分析模式（灯泡按钮）
  3) python broadcast.py            # 持续播报
     python broadcast.py --dry-run  # 只打印台词，不合成不播放（先验证 LLM）
     python broadcast.py --once     # 只播报一次
"""
import json
import os
import subprocess
import sys
import time
import uuid

import requests

# ==================== 配置（改成你的 key）====================
ARK_API_KEY = os.environ.get('ARK_API_KEY', '')   # 火山方舟 LLM 的 API Key
TTS_API_KEY = os.environ.get('TTS_API_KEY', '')   # 豆包语音 控制台>API Key管理 的 Key
LLM_MODEL   = os.environ.get('LLM_MODEL', '')     # 火山方舟接入点/模型 id，如 doubao-seed-1-6-250615
VOICE       = os.environ.get('VOICE', 'BV700_V2_streaming')  # 灿灿2.0 女声（免费，情感丰富）

STATE_URL   = os.environ.get('STATE_URL', 'http://127.0.0.1:8787/api/state')
LLM_URL     = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
TTS_URL     = 'https://openspeech.bytedance.com/api/v1/tts'

# 当前目录可 import 战术模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tactic_commentator as tc

# 对话历史（保持台词连贯）
HISTORY = []

SYSTEM_PROMPT = (
    "你是抖音象棋直播间的一名专业解说主播，声音自然、语速适中、语气生动有感染力。\n"
    "你要在对方还没落子前，用口语化、连贯、带感情的话，给观众讲当前这一手棋的走法和战术意图。\n"
    "要求：\n"
    "1. 像真人主播聊天，不是机器人播报；句子连贯，有语气起伏，适当带点情绪（惊叹、悬念、点评）。\n"
    "2. 结合给你的战术词（当头炮、跳马、进车压马、将军抽车、马后炮、重炮、捉双等），自然点出这手棋的看点。\n"
    "3. 每次只讲当前这一手，30~60字左右，纯口语，不要罗列术语，不要用书面语。\n"
    "4. 要和上一句衔接，显得一直在连续讲解，不要每次从零开始。\n"
    "5. 不要说“红方推荐”“AI 说”这类机器话，直接说“这步…”或“红方这步…”。\n"
    "只输出要说出口的那句台词，不要任何解释、不要引号、不要多余内容。"
)


def _check_keys():
    if not ARK_API_KEY:
        sys.exit("[!] 未配置 ARK_API_KEY（火山方舟 LLM key），请设环境变量或在脚本里填。")
    if not LLM_MODEL:
        sys.exit("[!] 未配置 LLM_MODEL（火山方舟接入点/模型 id），请填写。")
    if not TTS_API_KEY:
        sys.exit("[!] 未配置 TTS_API_KEY（豆包语音 API Key），请填写。")


def fetch_state():
    r = requests.get(STATE_URL, timeout=3)
    r.raise_for_status()
    return r.json()


# ---------------- LLM：生成台词 ----------------
def llm_line(user_text):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs += HISTORY[-6:]
    msgs.append({"role": "user", "content": user_text})
    payload = {
        "model": LLM_MODEL,
        "messages": msgs,
        "temperature": 0.9,
        "max_tokens": 200,
    }
    r = requests.post(LLM_URL, headers={
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    HISTORY.append({"role": "user", "content": user_text})
    HISTORY.append({"role": "assistant", "content": text})
    if len(HISTORY) > 8:
        del HISTORY[: len(HISTORY) - 8]
    return text


# ---------------- TTS：合成语音 ----------------
def tts_synth(text, out_path):
    reqid = str(uuid.uuid4())
    payload = {
        "app": {"appid": "", "token": "", "cluster": "volcano_tts"},
        "user": {"uid": "388808087185088"},
        "audio": {
            "voice_type": VOICE,
            "encoding": "wav",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {"reqid": reqid, "text": text, "operation": "query"},
    }
    r = requests.post(TTS_URL, headers={
        "X-Api-Key": TTS_API_KEY,
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    data = r.json()
    if data.get("code") != 3000:
        raise RuntimeError(f"TTS 失败: {data}")
    import base64
    audio_b64 = data["data"]["audio"]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(audio_b64))


# ---------------- 播放（Windows 原生 wav） ----------------
def play_wav(path):
    import winsound
    winsound.PlaySound(path, winsound.SND_FILENAME)


# ---------------- 组装 LLM 输入 ----------------
def build_user_text(state, verb, opening, tactics):
    fen = state.get('fen', '')
    red = state.get('redToMove', True)
    side = '红方' if red else '黑方'
    best = (state.get('analysis') or {}).get('best') or {}
    move_cn = best.get('bestMove', '') or ''
    best_move = best.get('bestMove', '')
    move_text = best.get('moveCn', '') or ''
    tactic_txt = '、'.join(tactics) if tactics else '普通一手'
    opening_txt = opening or ''
    return (
        f"当前局面(FEN)：{fen}\n"
        f"轮到：{side}\n"
        f"推荐走法：{side} 走 {move_cn}（{verb or move_text}）\n"
        f"战术/看点：{tactic_txt}（{opening_txt}）\n"
        f"请按主播人设，用一句连贯口语讲解这一手，30~60字。"
    )


def broadcast(state):
    board = state.get('board')
    if not board:
        return None
    best = (state.get('analysis') or {}).get('best') or {}
    move = best.get('bestMove') or ''
    move_cn = best.get('moveCn', '')
    if not move or len(move) != 4:
        return None
    # 复用战术分析
    b = [list(row) for row in board]
    after, frm, to, captured = tc.apply_move(b, move)
    opening_flag = tc.is_opening_position(state, b)
    verb, opening, tactics = tc.analyze_tactics(
        after, frm, to, move_cn or '', None, captured, opening_flag)
    user_text = build_user_text(state, verb, opening, tactics)
    line = llm_line(user_text)
    return line


def main():
    _check_keys()
    dry = '--dry-run' in sys.argv
    once = '--once' in sys.argv
    last_key = None
    last_ts = 0
    min_gap = float(os.environ.get('MIN_GAP', '8'))  # 同局面推荐抖动节流(秒)
    print(f"[播报] 轮询 {STATE_URL} | 音色 {VOICE} | dry_run={dry}")
    while True:
        try:
            state = fetch_state()
            best = (state.get('analysis') or {}).get('best') or {}
            move = best.get('bestMove') or ''
            key = (state.get('fen', ''), move)
            now = time.time()
            if move and key != last_key and (now - last_ts) >= min_gap:
                line = broadcast(state)
                if line:
                    print(f"\n>>> {line}\n")
                    last_key, last_ts = key, now
                    if not dry:
                        out = os.path.join(os.environ.get('TEMP', '.'), f'tts_{int(now)}.wav')
                        try:
                            tts_synth(line, out)
                            play_wav(out)
                        except Exception as e:
                            print(f"[!] 合成/播放失败: {e}")
                            print("    可先 python broadcast.py --dry-run 只验证台词。")
                    if once:
                        return
        except requests.RequestException as e:
            print(f"[!] 无法连接应用({STATE_URL})：{e}，请确认应用已启动且分析模式开启。")
        except Exception as e:
            print(f"[!] {type(e).__name__}: {e}")
        if once:
            return
        time.sleep(3)


if __name__ == '__main__':
    main()
