#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行棋前战术讲解：读取 TCHESS 的 /api/state，
基于引擎推荐的着法(bestMove)在走棋前分析战术，生成主播口语解说。

坐标约定（与 TCHESS 引擎一致）：
    着法 "a0b0" = 源列(a-i) 源行(0-9) 目标列 目标行
    列：a->0, b->1, ... i->8
    行：数字 0->9(红方底线), 9->0(黑方底线)
    棋盘 board[10][9]，board[y][x]，y=0 顶(黑方) ~ y=9 底(红方)
棋子：红大写 R N B A K C P，黑小写 r n b a k c p

用法：
    python tactic_commentator.py            # 打印一次解说
    python tactic_commentator.py --loop     # 每 3 秒轮询打印（直播用）
"""
import sys
import time
import requests

API = "http://127.0.0.1:8787/api/state"
PIECE_CN = {'K': '帅', 'A': '仕', 'B': '相', 'N': '马', 'R': '车', 'C': '炮', 'P': '兵',
            'k': '将', 'a': '士', 'b': '象', 'n': '马', 'r': '车', 'c': '炮', 'p': '卒'}

# ---------------------------------------------------------------- 基础工具

def is_red(p):
    return p != ' ' and p.isupper()


def is_enemy(p, side_red):
    return p != ' ' and is_red(p) != side_red


def parse_move(move):
    """'a0b0' -> (from(row,col), to(row,col))"""
    fx, fy = ord(move[0]) - 97, 9 - int(move[1])
    tx, ty = ord(move[2]) - 97, 9 - int(move[3])
    return (fy, fx), (ty, tx)


def apply_move(board, move):
    """返回走完 move 后的新棋盘，以及 (from, to, 被吃子字母)。"""
    (fy, fx), (ty, tx) = parse_move(move)
    b = [row[:] for row in board]
    captured = b[ty][tx]
    b[ty][tx] = b[fy][fx]
    b[fy][fx] = ' '
    return b, (fy, fx), (ty, tx), (captured if captured != ' ' else None)


def in_board(r, c):
    return 0 <= r <= 9 and 0 <= c <= 8


def find_king(board, side_red):
    k = 'K' if side_red else 'k'
    for r in range(10):
        for c in range(9):
            if board[r][c] == k:
                return r, c
    return None


# ---------------------------------------------------------------- 走法/攻击

def attacks(board, r, c):
    """返回该子能【吃】到的敌子位置集合（真实攻击，含将帅）。"""
    p = board[r][c]
    if p == ' ':
        return set()
    res = set()
    red = is_red(p)

    def add_capture(nr, nc):
        if in_board(nr, nc) and is_enemy(board[nr][nc], red):
            res.add((nr, nc))

    if p in 'Rr':                      # 车：横竖直走
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            while in_board(nr, nc):
                if board[nr][nc] == ' ':
                    nr, nc = nr + dr, nc + dc
                    continue
                if is_enemy(board[nr][nc], red):
                    res.add((nr, nc))
                break

    elif p in 'Cc':                    # 炮：隔一个子吃
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            jumped = False
            while in_board(nr, nc):
                cell = board[nr][nc]
                if cell == ' ':
                    nr, nc = nr + dr, nc + dc
                    continue
                if not jumped:         # 遇到第一个子作为炮架
                    jumped = True
                    nr, nc = nr + dr, nc + dc
                    continue
                if is_enemy(cell, red):  # 隔一个子后的第一个敌子可吃
                    res.add((nr, nc))
                break

    elif p in 'Nn':                    # 马：日字，蹩马腿
        jumps = ((2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0),
                 (1, 2, 0, 1), (-1, 2, 0, 1), (1, -2, 0, -1), (-1, -2, 0, -1))
        for dr, dc, br, bc in jumps:
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and board[r + br][c + bc] == ' ':
                add_capture(nr, nc)

    elif p in 'Pp':                    # 兵/卒
        if red:
            fwd = (-1, 0)
        else:
            fwd = (1, 0)
        nr, nc = r + fwd[0], c + fwd[1]
        add_capture(nr, nc)
        crossed = (r < 5) if red else (r >= 5)   # 过河后可横吃
        if crossed:
            add_capture(r, c + 1)
            add_capture(r, c - 1)

    elif p in 'Bb':                    # 象/相：田字，塞象眼，不过河
        if red:
            home = lambda rr: rr >= 5
        else:
            home = lambda rr: rr <= 4
        for dr, dc in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and home(nr) and board[r + dr // 2][c + dc // 2] == ' ':
                add_capture(nr, nc)

    elif p in 'Aa':                    # 士/仕：九宫斜走
        for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and 3 <= nc <= 5 and (0 <= nr <= 2 if not red else 7 <= nr <= 9):
                add_capture(nr, nc)

    elif p in 'Kk':                    # 帅/将：九宫直走一格（不含对脸）
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and 3 <= nc <= 5 and (0 <= nr <= 2 if not red else 7 <= nr <= 9):
                add_capture(nr, nc)
    return res


def is_check(board, side_red):
    """side_red 方是否正被将军（含将帅对脸）。"""
    king = find_king(board, side_red)
    if not king:
        return False
    kr, kc = king
    for r in range(10):
        for c in range(9):
            if is_enemy(board[r][c], side_red):
                if (kr, kc) in attacks(board, r, c):
                    return True
    # 将帅对脸
    for r in range(10):
        if board[r][kc] == ('K' if side_red else 'k'):
            pass
    opp = 'k' if side_red else 'K'
    if any(board[r][kc] == opp for r in range(10)):
        between = [board[r][kc] for r in range(kr, -1, -1) if board[r][kc] != ' ']
        # 与对方将同列且中间无子即对脸将军
        for r in range(10):
            if board[r][kc] == opp:
                lo, hi = min(r, kr), max(r, kr)
                if all(board[i][kc] == ' ' for i in range(lo + 1, hi)):
                    return True
    return False


# ---------------------------------------------------------------- 战术分析

def analyze_tactics(after_board, from_pos, to_pos, move_cn, mate, captured_piece=None):
    """在走完推荐着法后的局面上，分析这步棋的战术。"""
    r, c = to_pos
    piece = after_board[r][c]
    red = is_red(piece)
    side_txt = '红方' if red else '黑方'
    atk = attacks(after_board, r, c)

    tactics = []
    enemy_king = find_king(after_board, not red)
    checks = 1 if (enemy_king and enemy_king in atk) else 0
    capturable = [pos for pos in atk if not (enemy_king and pos == enemy_king)]

    if checks:
        tactics.append('将杀' if mate else '将军')
    if captured_piece:
        tactics.append('吃掉对方' + PIECE_CN.get(captured_piece, '子'))
    if len(capturable) >= 2:
        tactics.append('捉双')
    elif len(capturable) == 1:
        tactics.append('捉' + PIECE_CN.get(after_board[capturable[0][0]][capturable[0][1]], '子'))
    return side_txt, tactics, capturable


# ---------------------------------------------------------------- 开局名

OPENINGS = {
    '炮二平五': '当头炮', '炮八平五': '当头炮',
    '兵三进一': '仙人指路', '兵七进一': '仙人指路',
    '相三进五': '飞相局', '相七进五': '飞相局',
    '马二进三': '起马局', '马八进七': '起马局',
    '炮八进二': '左炮巡河', '炮2进2': '右炮巡河',
    '炮二平六': '过宫炮', '炮八平六': '过宫炮',
    '炮二平四': '仕角炮', '炮八平三': '左炮平三',
}


# ---------------------------------------------------------------- 解说

def comment(state):
    best = state['analysis']['best']
    if not best:
        return '引擎暂无分析，请先开启分析模式。'
    move = best['bestMove']                     # 如 a0b0
    move_cn = best['moveCn'].split()[0]         # 本步中文着法
    board = state['board']                      # 10x9
    side = state['sideToMove']
    mate = best['mate']

    after, frm, to, captured = apply_move(board, move)
    side_txt, tactics, capturable = analyze_tactics(after, frm, to, move_cn, mate, captured)

    parts = [f'{side_txt}推荐走：{move_cn}']
    opening = OPENINGS.get(move_cn)
    if opening:
        parts.append(f'（{opening}）')
    if tactics:
        parts.append('，' + '、'.join(tactics))
    parts.append(f'。评估分 {best["score"]}，深度 {best["depth"]}')
    return ''.join(parts)


# ---------------------------------------------------------------- 主流程

def fetch():
    r = requests.get(API, timeout=3)
    return r.json()


def main():
    loop = '--loop' in sys.argv
    last = None
    while True:
        try:
            s = fetch()
            txt = comment(s)
            if txt != last:
                print(txt, flush=True)
                last = txt
        except Exception as e:
            print('请求失败:', e, flush=True)
        if not loop:
            break
        time.sleep(3)


if __name__ == '__main__':
    main()
